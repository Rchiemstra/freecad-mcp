"""Screenshot and view-sequence RPC methods (Phase 4 slice 4G)."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

import FreeCAD
import FreeCADGui

from ...gui_ops_view_encode import encode_png_file
from ...gui_ops_view_sequence import (
    capture_view_sequence_gui,
    capture_view_sequence_to_disk_gui,
)
from ...view_manager import save_active_screenshot

logger = logging.getLogger("FreeCADMCP.rpc_server")


def get_active_screenshot(
    self,
    view_name: str | None = "Isometric",
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
    focus_objects: list[str] | None = None,
    yaw_deg: float | None = None,
) -> str:
    """Get a screenshot of the active view.

    Returns a base64-encoded string of the screenshot or None if a screenshot
    cannot be captured (e.g., when in TechDraw or Spreadsheet view).
    """

    def check_view_supports_screenshots():
        try:
            active_view = FreeCADGui.ActiveDocument.ActiveView
            if active_view is None:
                FreeCAD.Console.PrintWarning("No active view available\n")
                return False

            view_type = type(active_view).__name__
            has_save_image = hasattr(active_view, "saveImage")
            FreeCAD.Console.PrintMessage(
                f"View type: {view_type}, Has saveImage: {has_save_image}\n"
            )
            return has_save_image
        except Exception as exc:
            FreeCAD.Console.PrintError(f"Error checking view capabilities: {exc}\n")
            return False

    supports_screenshots = self._dispatch_gui(check_view_supports_screenshots)

    if not supports_screenshots:
        logger.warning("Current view does not support screenshots")
        return None

    fd, tmp_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    res = self._dispatch_gui(
        lambda: save_active_screenshot(
            tmp_path,
            view_name or "Isometric",
            width,
            height,
            focus_object=focus_object,
            focus_objects=focus_objects,
            yaw_deg=yaw_deg,
        )
    )
    if res is True:
        try:
            encoded = encode_png_file(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        return encoded
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    logger.warning("Failed to capture screenshot: %s", res)
    return None


def capture_view_sequence(
    self,
    frames: list[dict[str, Any]] | None = None,
    width: int | None = None,
    height: int | None = None,
    orbit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture multiple framed screenshots and return base64 PNG payloads."""

    try:
        return self._dispatch_gui(
            lambda: capture_view_sequence_gui(
                frames=frames,
                width=width,
                height=height,
                orbit=orbit,
            )
        )
    except Exception as exc:
        logger.exception("capture_view_sequence failed")
        return {"ok": False, "error": str(exc), "frames": []}


def capture_view_sequence_to_disk(
    self,
    frames: list[dict[str, Any]] | None = None,
    width: int | None = None,
    height: int | None = None,
    orbit: dict[str, Any] | None = None,
    frame_dir: str | None = None,
) -> dict[str, Any]:
    """Capture frames to a directory and return PNG paths (for ffmpeg)."""

    try:
        return self._dispatch_gui(
            lambda: capture_view_sequence_to_disk_gui(
                frames=frames,
                width=width,
                height=height,
                orbit=orbit,
                frame_dir=frame_dir,
            )
        )
    except Exception as exc:
        logger.exception("capture_view_sequence_to_disk failed")
        return {"ok": False, "error": str(exc), "frame_paths": []}


__all__ = [
    "capture_view_sequence",
    "capture_view_sequence_to_disk",
    "get_active_screenshot",
]
