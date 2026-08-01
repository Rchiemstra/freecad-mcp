"""Read-only GUI context snapshot helpers."""

from __future__ import annotations

from typing import Any

import FreeCAD
import FreeCADGui

from .selection_ops import get_selection


def get_gui_state() -> dict[str, Any]:
    """Read-only snapshot of the active GUI context.

    Reports the active document, active PartDesign Body, active workbench, the
    object currently in edit-mode, and the current selection. Every probe is
    guarded so a headless or partially-initialised GUI degrades to ``None``
    rather than raising.
    """
    state: dict[str, Any] = {"ok": True}

    try:
        app_doc = FreeCAD.ActiveDocument
        state["active_document"] = app_doc.Name if app_doc else None
        state["active_document_label"] = app_doc.Label if app_doc else None
    except Exception as exc:
        state["active_document"] = None
        state["active_document_error"] = str(exc)

    try:
        wb = FreeCADGui.activeWorkbench()
        state["active_workbench"] = (
            wb.name() if hasattr(wb, "name") else type(wb).__name__
        )
    except Exception as exc:
        state["active_workbench"] = None
        state["active_workbench_error"] = str(exc)

    try:
        gui_doc = FreeCADGui.ActiveDocument
        if gui_doc is not None:
            in_edit = gui_doc.getInEdit()
            edit_obj = getattr(in_edit, "Object", None) if in_edit is not None else None
            state["edit_mode_object"] = getattr(edit_obj, "Name", None)
            try:
                view = gui_doc.activeView()
            except Exception:
                view = None
            active_body = None
            if view is not None and hasattr(view, "getActiveObject"):
                active_body = view.getActiveObject("pdbody")
            state["active_body"] = getattr(active_body, "Name", None)
        else:
            state["edit_mode_object"] = None
            state["active_body"] = None
    except Exception as exc:
        state["active_body"] = None
        state["edit_mode_object"] = None
        state["edit_mode_error"] = str(exc)

    try:
        sel = get_selection()
        state["selection"] = sel.get("selection", [])
        state["selection_count"] = sel.get("count", 0)
    except Exception as exc:
        state["selection"] = []
        state["selection_error"] = str(exc)

    return state


__all__ = ["get_gui_state"]
