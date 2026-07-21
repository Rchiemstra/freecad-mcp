"""Active-view orientation, sizing, and screenshot capture."""

from __future__ import annotations

from typing import Any, Sequence

import FreeCAD
import FreeCADGui

from .gui_dispatch import _flush_gui_events


_VIEW_DISPATCH = {
    "Isometric": "viewIsometric",
    "Front": "viewFront",
    "Top": "viewTop",
    "Right": "viewRight",
    "Back": "viewBack",
    "Left": "viewLeft",
    "Bottom": "viewBottom",
    "Dimetric": "viewDimetric",
    "Trimetric": "viewTrimetric",
}

_STD_COMMAND_DISPATCH = {
    "Isometric": "Std_ViewIsometric",
    "Front": "Std_ViewFront",
    "Top": "Std_ViewTop",
    "Right": "Std_ViewRight",
    "Back": "Std_ViewRear",
    "Left": "Std_ViewLeft",
    "Bottom": "Std_ViewBottom",
    "Dimetric": "Std_ViewDimetric",
    "Trimetric": "Std_ViewTrimetric",
}


def _normalize_focus_names(
    focus_object: str | None = None,
    focus_objects: Sequence[str] | None = None,
) -> list[str]:
    names: list[str] = []
    if focus_objects:
        names.extend(str(name) for name in focus_objects if str(name))
    if focus_object:
        # Allow comma-separated names for backward-compatible agents.
        for part in str(focus_object).split(","):
            part = part.strip()
            if part and part not in names:
                names.append(part)
    return names


def _get_view_size(view: Any) -> tuple[int, int]:
    try:
        size = view.getSize()
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            return max(1, int(size[0])), max(1, int(size[1]))
        return max(1, int(size.width())), max(1, int(size.height()))
    except Exception:
        return 1024, 768


def _resolve_screenshot_size(
    view: Any,
    width: int | None,
    height: int | None,
) -> tuple[int, int]:
    view_width, view_height = _get_view_size(view)
    resolved_width = view_width if width is None else max(1, int(width))
    resolved_height = view_height if height is None else max(1, int(height))
    return resolved_width, resolved_height


def apply_view_orientation(view: Any, view_name: str) -> None:
    aliases = {
        "Rear": "Back",
        "Side": "Right",
        "SideRight": "Right",
        "SideLeft": "Left",
    }
    view_name = aliases.get(str(view_name), str(view_name))
    method_name = _VIEW_DISPATCH.get(view_name)
    if method_name is None:
        raise ValueError(f"Invalid view name: {view_name}")
    if hasattr(view, method_name):
        getattr(view, method_name)()
    else:
        cmd = _STD_COMMAND_DISPATCH.get(view_name)
        if cmd:
            FreeCADGui.runCommand(cmd)
        else:
            FreeCAD.Console.PrintWarning(
                f"apply_view_orientation: no method or command for '{view_name}'\n"
            )


def _resolve_focus_targets(names: Sequence[str]) -> list[Any]:
    doc = FreeCAD.ActiveDocument
    if not doc:
        return []
    targets = []
    for name in names:
        obj = doc.getObject(name)
        if obj is not None:
            targets.append(obj)
    return targets


def _frame_on_targets(view: Any, targets: Sequence[Any]) -> bool:
    """Select targets and frame the view. Returns True when a selection was used."""
    if not targets:
        view.fitAll()
        return False
    FreeCADGui.Selection.clearSelection()
    for obj in targets:
        FreeCADGui.Selection.addSelection(obj)
    FreeCADGui.SendMsgToActiveView("ViewSelection")
    return True


def _apply_yaw(view: Any, yaw_deg: float | None) -> None:
    if yaw_deg is None:
        return
    try:
        # Rotate camera around the view's up axis after framing.
        if hasattr(view, "setCameraOrientation"):
            current = view.getCameraOrientation()
            extra = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), float(yaw_deg))
            view.setCameraOrientation((extra * FreeCAD.Rotation(*current)).Q)
        elif hasattr(view, "viewRotateLeft"):
            # Approximate: FreeCAD's rotate-left is ~10° per call.
            steps = int(round(float(yaw_deg) / 10.0)) % 36
            for _ in range(max(0, steps)):
                view.viewRotateLeft()
    except Exception as exc:
        FreeCAD.Console.PrintWarning(f"view yaw apply failed: {exc}\n")


def save_active_screenshot(
    save_path: str,
    view_name: str = "Isometric",
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
    focus_objects: Sequence[str] | None = None,
    yaw_deg: float | None = None,
):
    """Save a PNG of the active view to ``save_path``.

    Returns ``True`` on success, or an error string on failure (preserves the
    legacy GUI-handler return contract).
    """
    try:
        view = FreeCADGui.ActiveDocument.ActiveView
        if not hasattr(view, "saveImage"):
            return "Current view does not support screenshots"

        apply_view_orientation(view, view_name)

        focus_names = _normalize_focus_names(focus_object, focus_objects)
        targets = _resolve_focus_targets(focus_names)
        focused_selection = _frame_on_targets(view, targets)
        _flush_gui_events()
        if focused_selection:
            FreeCADGui.Selection.clearSelection()

        # Re-issue framing synchronously right before saveImage (macOS blank-frame fix).
        if focused_selection:
            FreeCADGui.Selection.clearSelection()
            for obj in targets:
                FreeCADGui.Selection.addSelection(obj)
            FreeCADGui.SendMsgToActiveView("ViewSelection")
            FreeCADGui.Selection.clearSelection()
        else:
            view.fitAll()

        _apply_yaw(view, yaw_deg)
        _flush_gui_events()

        resolved_width, resolved_height = _resolve_screenshot_size(view, width, height)
        view.saveImage(save_path, resolved_width, resolved_height, "Current")

        if focused_selection:
            FreeCADGui.Selection.clearSelection()
            _flush_gui_events(delay_ms=0)
        return True
    except Exception as e:
        return str(e)


def save_view_sequence(
    frames: Sequence[dict[str, Any]],
    width: int | None = None,
    height: int | None = None,
) -> list[dict[str, Any]]:
    """Capture multiple framed screenshots.

    Each frame dict accepts:
    - ``view_name`` (default Isometric)
    - ``focus_object`` / ``focus_objects``
    - ``yaw_deg``
    - ``label``
    - ``path`` (required output PNG path)
    """
    results: list[dict[str, Any]] = []
    for index, frame in enumerate(frames):
        path = frame.get("path")
        if not path:
            results.append({"index": index, "ok": False, "error": "frame.path is required"})
            continue
        status = save_active_screenshot(
            str(path),
            view_name=str(frame.get("view_name") or "Isometric"),
            width=width if frame.get("width") is None else frame.get("width"),
            height=height if frame.get("height") is None else frame.get("height"),
            focus_object=frame.get("focus_object"),
            focus_objects=frame.get("focus_objects"),
            yaw_deg=frame.get("yaw_deg"),
        )
        results.append({
            "index": index,
            "ok": status is True,
            "error": None if status is True else str(status),
            "path": str(path),
            "label": frame.get("label") or f"frame_{index}",
            "view_name": frame.get("view_name") or "Isometric",
            "focus_objects": _normalize_focus_names(
                frame.get("focus_object"), frame.get("focus_objects")
            ),
            "yaw_deg": frame.get("yaw_deg"),
        })
    return results


def build_orbit_frames(
    *,
    focus_objects: Sequence[str] | None = None,
    focus_object: str | None = None,
    steps: int = 8,
    view_name: str = "Isometric",
    elevation_yaw_start_deg: float = 0.0,
) -> list[dict[str, Any]]:
    """Build yaw-orbit frame descriptors around the current focus."""
    names = _normalize_focus_names(focus_object, focus_objects)
    count = max(2, int(steps))
    frames = []
    for i in range(count):
        yaw = elevation_yaw_start_deg + (360.0 * i / count)
        frames.append({
            "view_name": view_name,
            "focus_objects": names,
            "yaw_deg": yaw,
            "label": f"orbit_{i:02d}",
        })
    return frames


def refresh_active_view(
    *,
    focus_object: str | None = None,
    focus_objects: Sequence[str] | None = None,
    touch_objects: Sequence[str] | None = None,
    fit: bool = False,
) -> dict[str, Any]:
    """Force a GUI redraw; optionally touch Placement and reframe."""
    try:
        view = FreeCADGui.ActiveDocument.ActiveView
        doc = FreeCAD.ActiveDocument
        touched = []
        for name in touch_objects or []:
            obj = doc.getObject(name) if doc else None
            if obj is None or not hasattr(obj, "Placement"):
                continue
            obj.Placement = obj.Placement
            touched.append(name)
        FreeCADGui.updateGui()
        _flush_gui_events()
        focus_names = _normalize_focus_names(focus_object, focus_objects)
        targets = _resolve_focus_targets(focus_names)
        framed = False
        if fit or targets:
            framed = _frame_on_targets(view, targets) if targets else False
            if not targets:
                view.fitAll()
            FreeCADGui.Selection.clearSelection()
            _flush_gui_events()
        return {
            "ok": True,
            "touched": touched,
            "focus_objects": focus_names,
            "framed": framed or bool(fit),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


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
    import os
    import tempfile

    import Part

    doc = FreeCAD.getDocument(doc_name)
    if doc is None:
        return {"ok": False, "error": f"Document {doc_name!r} not found"}
    obj = doc.getObject(obj_name)
    if obj is None or not hasattr(obj, "Placement"):
        return {"ok": False, "error": f"Object {obj_name!r} not found or has no Placement"}

    positions: list[dict[str, Any]] = []
    if keyframes:
        for index, sample in enumerate(keyframes):
            if not isinstance(sample, dict):
                return {"ok": False, "error": "Each keyframe must be a dict with x/y/z"}
            positions.append({
                "index": index,
                "x": float(sample["x"]),
                "y": float(sample["y"]),
                "z": float(sample["z"]),
                "yaw_deg": float(sample["yaw_deg"]) if "yaw_deg" in sample else None,
            })
    elif path_object:
        path_obj = doc.getObject(path_object)
        if path_obj is None or not hasattr(path_obj, "Shape"):
            return {"ok": False, "error": f"Path object {path_object!r} not found"}
        edges = list(getattr(path_obj.Shape, "Edges", []) or [])
        if not edges:
            return {"ok": False, "error": f"Path object {path_object!r} has no edges"}
        try:
            wire = Part.Wire(edges)
        except Exception:
            wire = edges[0]
        count = max(2, int(sample_count))
        try:
            pts = list(wire.discretize(Number=count))
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
        for index, pt in enumerate(pts):
            positions.append({
                "index": index,
                "x": float(pt.x),
                "y": float(pt.y),
                "z": float(pt.z),
                "yaw_deg": None,
            })
    else:
        return {"ok": False, "error": "Provide keyframes or path_object"}

    out_dir = frame_dir or tempfile.mkdtemp(prefix="mcp_anim_")
    os.makedirs(out_dir, exist_ok=True)
    original = FreeCAD.Placement(obj.Placement)
    focus_names = _normalize_focus_names(None, focus_objects) or [obj_name]
    frames: list[dict[str, Any]] = []
    restored = False
    try:
        for sample in positions:
            base = FreeCAD.Vector(sample["x"], sample["y"], sample["z"])
            rot = original.Rotation
            if sample["yaw_deg"] is not None:
                rot = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), float(sample["yaw_deg"]))
            obj.Placement = FreeCAD.Placement(base, rot)
            refresh_active_view(focus_objects=focus_names, touch_objects=[obj_name], fit=True)
            path = os.path.join(out_dir, f"frame_{sample['index']:03d}.png")
            status = save_active_screenshot(
                path,
                view_name=view_name,
                width=width,
                height=height,
                focus_objects=focus_names,
            )
            frames.append({
                "index": sample["index"],
                "ok": status is True,
                "error": None if status is True else str(status),
                "path": path,
                "label": f"anim_{sample['index']:02d}",
                "position": [sample["x"], sample["y"], sample["z"]],
                "yaw_deg": sample["yaw_deg"],
            })
    finally:
        try:
            obj.Placement = original
            refresh_active_view(touch_objects=[obj_name])
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
