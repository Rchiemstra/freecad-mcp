"""View sequence frame preparation helpers for GUI RPC methods."""

from __future__ import annotations

import os
import tempfile
from typing import Any

from .gui_ops_view_encode import cleanup_temp_dir, encode_view_sequence_frames
from .view_manager import build_orbit_frames, save_view_sequence


def merge_orbit_and_frame_specs(
    frames: list[dict[str, Any]] | None,
    orbit: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    work_frames: list[dict[str, Any]] = []
    if orbit:
        work_frames.extend(
            build_orbit_frames(
                focus_objects=orbit.get("focus_objects"),
                focus_object=orbit.get("focus_object"),
                steps=int(orbit.get("steps") or 8),
                view_name=str(orbit.get("view_name") or "Isometric"),
                elevation_yaw_start_deg=float(orbit.get("yaw_start_deg") or 0.0),
            )
        )
    if frames:
        work_frames.extend(frames)
    return work_frames


def capture_view_sequence_gui(
    frames: list[dict[str, Any]] | None = None,
    width: int | None = None,
    height: int | None = None,
    orbit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    work_frames = merge_orbit_and_frame_specs(frames, orbit)
    if not work_frames:
        return {
            "ok": False,
            "error": "Provide frames and/or orbit",
            "frames": [],
        }

    tmp_dir = tempfile.mkdtemp(prefix="mcp_view_seq_")
    prepared = []
    for index, frame in enumerate(work_frames):
        item = dict(frame)
        item["path"] = os.path.join(tmp_dir, f"frame_{index:03d}.png")
        prepared.append(item)
    results = save_view_sequence(prepared, width=width, height=height)
    encoded_frames = encode_view_sequence_frames(results)
    cleanup_temp_dir(tmp_dir)
    ok_count = sum(
        1 for frame in encoded_frames if frame["ok"] and frame["image_base64"]
    )
    return {
        "ok": ok_count > 0,
        "frame_count": len(encoded_frames),
        "ok_count": ok_count,
        "frames": encoded_frames,
    }


def capture_view_sequence_to_disk_gui(
    frames: list[dict[str, Any]] | None = None,
    width: int | None = None,
    height: int | None = None,
    orbit: dict[str, Any] | None = None,
    frame_dir: str | None = None,
) -> dict[str, Any]:
    work_frames = merge_orbit_and_frame_specs(frames, orbit)
    if not work_frames:
        return {
            "ok": False,
            "error": "Provide frames and/or orbit",
            "frame_paths": [],
        }
    out_dir = frame_dir or tempfile.mkdtemp(prefix="mcp_view_disk_")
    os.makedirs(out_dir, exist_ok=True)
    prepared = []
    for index, frame in enumerate(work_frames):
        item = dict(frame)
        item["path"] = os.path.join(out_dir, f"frame_{index:03d}.png")
        prepared.append(item)
    results = save_view_sequence(prepared, width=width, height=height)
    paths = [item["path"] for item in results if item.get("ok")]
    return {
        "ok": bool(paths),
        "frame_dir": out_dir,
        "frame_count": len(results),
        "ok_count": len(paths),
        "frame_paths": paths,
        "frames": results,
    }


__all__ = [
    "capture_view_sequence_gui",
    "capture_view_sequence_to_disk_gui",
    "merge_orbit_and_frame_specs",
]
