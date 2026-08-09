"""Temporary placement animation with screenshot capture."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from typing import Any

import FreeCAD

from .focus_helpers import normalize_focus_names
from .refresh_view import refresh_active_view
from .screenshot import save_active_screenshot


def _positions_from_keyframes(
    keyframes: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    positions: list[dict[str, Any]] = []
    for index, sample in enumerate(keyframes):
        if not isinstance(sample, dict):
            return None, {"ok": False, "error": "Each keyframe must be a dict with x/y/z"}
        positions.append({
            "index": index,
            "x": float(sample["x"]),
            "y": float(sample["y"]),
            "z": float(sample["z"]),
            "yaw_deg": float(sample["yaw_deg"]) if "yaw_deg" in sample else None,
        })
    return positions, None


def _discretize_wire(wire: Any, edges: list[Any], count: int) -> list[Any]:
    try:
        return list(wire.discretize(Number=count))
    except Exception:
        length = float(getattr(wire, "Length", 0.0) or 0.0)
        pts = []
        for i in range(count):
            u = 0.0 if count == 1 else i / float(count - 1)
            if hasattr(wire, "valueAt") and length > 0:
                pts.append(wire.valueAt(u * length))
            else:
                edge = edges[0]
                pts.append(
                    edge.valueAt(
                        edge.FirstParameter
                        + u * (edge.LastParameter - edge.FirstParameter)
                    )
                )
        return pts


def _positions_from_path(
    doc: Any,
    path_object: str,
    sample_count: int,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    import Part

    path_obj = doc.getObject(path_object)
    if path_obj is None or not hasattr(path_obj, "Shape"):
        return None, {"ok": False, "error": f"Path object {path_object!r} not found"}
    edges = list(getattr(path_obj.Shape, "Edges", []) or [])
    if not edges:
        return None, {"ok": False, "error": f"Path object {path_object!r} has no edges"}
    try:
        wire = Part.Wire(edges)
    except Exception:
        wire = edges[0]
    count = max(2, int(sample_count))
    pts = _discretize_wire(wire, edges, count)
    positions = [
        {
            "index": index,
            "x": float(pt.x),
            "y": float(pt.y),
            "z": float(pt.z),
            "yaw_deg": None,
        }
        for index, pt in enumerate(pts)
    ]
    return positions, None


def _resolve_animation_positions(
    doc: Any,
    *,
    keyframes: Sequence[dict[str, Any]] | None,
    path_object: str | None,
    sample_count: int,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    if keyframes:
        return _positions_from_keyframes(keyframes)
    if path_object:
        return _positions_from_path(doc, path_object, sample_count)
    return None, {"ok": False, "error": "Provide keyframes or path_object"}


def _placement_for_sample(original: FreeCAD.Placement, sample: dict[str, Any]) -> FreeCAD.Placement:
    base = FreeCAD.Vector(sample["x"], sample["y"], sample["z"])
    rot = original.Rotation
    if sample["yaw_deg"] is not None:
        rot = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), float(sample["yaw_deg"]))
    return FreeCAD.Placement(base, rot)


def _capture_animation_frame(
    obj: Any,
    sample: dict[str, Any],
    original: FreeCAD.Placement,
    *,
    out_dir: str,
    view_name: str,
    width: int | None,
    height: int | None,
    focus_names: list[str],
) -> dict[str, Any]:
    obj.Placement = _placement_for_sample(original, sample)
    refresh_active_view(focus_objects=focus_names, fit=True)
    path = os.path.join(out_dir, f"frame_{sample['index']:03d}.png")
    status = save_active_screenshot(
        path,
        view_name=view_name,
        width=width,
        height=height,
        focus_objects=focus_names,
    )
    return {
        "index": sample["index"],
        "ok": status is True,
        "error": None if status is True else str(status),
        "path": path,
        "label": f"anim_{sample['index']:02d}",
        "position": [sample["x"], sample["y"], sample["z"]],
        "yaw_deg": sample["yaw_deg"],
    }


def animate_object_placement(
    doc_name: str,
    obj_name: str,
    *,
    keyframes: Sequence[dict[str, Any]] | None = None,
    path_object: str | None = None,
    sample_count: int = 12,
    view_name: str = "Isometric",
    focus_objects: Sequence[str] | None = None,
    width: int | None = None,
    height: int | None = None,
    frame_dir: str | None = None,
) -> dict[str, Any]:
    """Temporarily move ``Placement`` along samples, capture frames, then restore."""
    doc = FreeCAD.getDocument(doc_name)
    if doc is None:
        return {"ok": False, "error": f"Document {doc_name!r} not found"}
    obj = doc.getObject(obj_name)
    if obj is None or not hasattr(obj, "Placement"):
        return {"ok": False, "error": f"Object {obj_name!r} not found or has no Placement"}

    positions, error = _resolve_animation_positions(
        doc,
        keyframes=keyframes,
        path_object=path_object,
        sample_count=sample_count,
    )
    if error is not None:
        return error

    out_dir = frame_dir or tempfile.mkdtemp(prefix="mcp_anim_")
    os.makedirs(out_dir, exist_ok=True)
    original = FreeCAD.Placement(obj.Placement)
    focus_names = normalize_focus_names(None, focus_objects) or [obj_name]
    frames: list[dict[str, Any]] = []
    restored = False
    try:
        for sample in positions:
            frames.append(
                _capture_animation_frame(
                    obj,
                    sample,
                    original,
                    out_dir=out_dir,
                    view_name=view_name,
                    width=width,
                    height=height,
                    focus_names=focus_names,
                )
            )
    finally:
        try:
            obj.Placement = original
            refresh_active_view()
            restored = True
        except Exception:
            restored = False

    ok_count = sum(1 for frame in frames if frame["ok"])
    return {
        "ok": restored,
        "frame_dir": out_dir,
        "frame_count": len(frames),
        "ok_count": ok_count,
        "restored": restored,
        "frames": frames,
        "focus_objects": focus_names,
        "screenshot_ok": ok_count == len(frames) and len(frames) > 0,
    }
