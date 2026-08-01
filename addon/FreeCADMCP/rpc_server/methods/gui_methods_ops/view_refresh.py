"""View refresh, placement repair, and animation RPC methods (Phase 4 slice 4G)."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from ...gui_ops_view_encode import encode_png_file
from ...view_manager import (
    animate_object_placement,
    refresh_active_view,
    repair_placements_and_refresh,
    save_active_screenshot,
)

logger = logging.getLogger("FreeCADMCP.rpc_server")


def refresh_view(
    self,
    focus_objects: list[str] | None = None,
    focus_object: str | None = None,
    touch_objects: list[str] | None = None,
    fit: bool = False,
    capture: bool = False,
    view_name: str = "Isometric",
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        result = refresh_active_view(
            focus_object=focus_object,
            focus_objects=focus_objects,
            fit=fit,
        )
        if not result.get("ok"):
            return result
        if capture:
            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            status = save_active_screenshot(
                tmp_path,
                view_name=view_name,
                width=width,
                height=height,
                focus_object=focus_object,
                focus_objects=focus_objects,
            )
            if status is True:
                result["image_base64"] = encode_png_file(tmp_path)
            else:
                result["capture_error"] = str(status)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        return result

    try:
        if touch_objects:
            return {
                "ok": False,
                "error_code": "PLACEMENT_REPAIR_REQUIRES_LEASE",
                "error": (
                    "refresh_view is visual-only; use repair_view_placements "
                    "with an explicit leased document"
                ),
            }
        return self._dispatch_gui(_run)
    except Exception as exc:
        logger.exception("refresh_view failed")
        return {"ok": False, "error": str(exc)}


def repair_view_placements(
    self,
    doc_name: str,
    touch_objects: list[str],
    fit: bool = False,
) -> dict[str, Any]:
    return self._dispatch_gui(
        lambda: repair_placements_and_refresh(doc_name, touch_objects, fit=fit)
    )


def animate_placement(
    self,
    doc_name: str,
    obj_name: str,
    keyframes: list[dict[str, Any]] | None = None,
    path_object: str | None = None,
    sample_count: int = 12,
    view_name: str = "Isometric",
    focus_objects: list[str] | None = None,
    width: int | None = None,
    height: int | None = None,
    encode_video: bool = False,
    fps: float = 8.0,
    output_path: str | None = None,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        result = animate_object_placement(
            doc_name,
            obj_name,
            keyframes=keyframes,
            path_object=path_object,
            sample_count=sample_count,
            view_name=view_name,
            focus_objects=focus_objects,
            width=width,
            height=height,
        )
        if not result.get("ok"):
            return result
        encoded_frames = []
        for frame in result.get("frames", []):
            payload = dict(frame)
            path = frame.get("path")
            if frame.get("ok") and path and os.path.exists(path):
                payload["image_base64"] = encode_png_file(path)
            encoded_frames.append(payload)
        result["frames"] = encoded_frames
        return result

    try:
        return self._dispatch_gui(_run)
    except Exception as exc:
        logger.exception("animate_placement failed")
        return {"ok": False, "error": str(exc)}


__all__ = [
    "animate_placement",
    "refresh_view",
    "repair_view_placements",
]
