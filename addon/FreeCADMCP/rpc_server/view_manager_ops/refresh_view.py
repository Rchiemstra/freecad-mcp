"""Active-view redraw and optional camera reframe."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import FreeCADGui

from ..gui_dispatch import _flush_gui_events
from .focus_helpers import (
    frame_on_targets,
    normalize_focus_names,
    resolve_focus_targets,
)


def refresh_active_view(
    *,
    focus_object: str | None = None,
    focus_objects: Sequence[str] | None = None,
    fit: bool = False,
) -> dict[str, Any]:
    """Force a strictly visual GUI redraw and optional camera reframe."""
    try:
        view = FreeCADGui.ActiveDocument.ActiveView
        FreeCADGui.updateGui()
        _flush_gui_events()
        focus_names = normalize_focus_names(focus_object, focus_objects)
        targets = resolve_focus_targets(focus_names)
        framed = False
        if fit or targets:
            framed = frame_on_targets(view, targets) if targets else False
            if not targets:
                view.fitAll()
            FreeCADGui.Selection.clearSelection()
            _flush_gui_events()
        return {
            "ok": True,
            "touched": [],
            "focus_objects": focus_names,
            "framed": framed or bool(fit),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
