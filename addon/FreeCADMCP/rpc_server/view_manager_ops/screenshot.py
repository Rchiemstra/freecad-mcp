"""Active-view screenshot capture."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import FreeCADGui

from ..gui_dispatch import _flush_gui_events
from .focus_helpers import (
    apply_yaw,
    frame_on_targets,
    normalize_focus_names,
    resolve_focus_targets,
)
from .view_constants import apply_view_orientation


def get_view_size(view: Any) -> tuple[int, int]:
    try:
        size = view.getSize()
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            return max(1, int(size[0])), max(1, int(size[1]))
        return max(1, int(size.width())), max(1, int(size.height()))
    except Exception:
        return 1024, 768


def resolve_screenshot_size(
    view: Any,
    width: int | None,
    height: int | None,
) -> tuple[int, int]:
    view_width, view_height = get_view_size(view)
    resolved_width = view_width if width is None else max(1, int(width))
    resolved_height = view_height if height is None else max(1, int(height))
    return resolved_width, resolved_height


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

        focus_names = normalize_focus_names(focus_object, focus_objects)
        targets = resolve_focus_targets(focus_names)
        focused_selection = frame_on_targets(view, targets)
        _flush_gui_events()
        if focused_selection:
            FreeCADGui.Selection.clearSelection()

        if focused_selection:
            FreeCADGui.Selection.clearSelection()
            for obj in targets:
                FreeCADGui.Selection.addSelection(obj)
            FreeCADGui.SendMsgToActiveView("ViewSelection")
            FreeCADGui.Selection.clearSelection()
        else:
            view.fitAll()

        apply_yaw(view, yaw_deg)
        _flush_gui_events()

        resolved_width, resolved_height = resolve_screenshot_size(view, width, height)
        view.saveImage(save_path, resolved_width, resolved_height, "Current")

        if focused_selection:
            FreeCADGui.Selection.clearSelection()
            _flush_gui_events(delay_ms=0)
        return True
    except Exception as e:
        return str(e)
