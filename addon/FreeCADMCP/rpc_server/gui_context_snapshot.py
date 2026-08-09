"""Read-only named-document GUI context capture."""

from __future__ import annotations


def _view_name(viewport):
    for attribute in ("getName", "objectName", "windowTitle"):
        value = getattr(viewport, attribute, None)
        if not callable(value):
            continue
        try:
            name = str(value() or "")
        except Exception:
            continue
        if name:
            return name
    return ""


def _workbench_name(gui_module):
    try:
        workbench = gui_module.activeWorkbench()
        return str(
            workbench.name() if hasattr(workbench, "name") else type(workbench).__name__
        )
    except Exception:
        return ""


def _edit_focus(gui_document):
    try:
        in_edit = gui_document.getInEdit()
        return str(getattr(getattr(in_edit, "Object", None), "Name", "") or "")
    except Exception:
        return ""


def _active_body(viewport):
    try:
        body = viewport.getActiveObject("pdbody")
        return str(getattr(body, "Name", "") or "")
    except Exception:
        return ""


def _viewport_size(viewport):
    try:
        width, height = viewport.getSize()
        width, height = int(width), int(height)
        if width > 0 and height > 0:
            return width, height
    except Exception:
        pass
    return 1, 1


def capture_baseline(gui_module, document_name):
    gui_document = gui_module.getDocument(document_name)
    if gui_document is None:
        raise RuntimeError(f"GUI document not found: {document_name}")
    viewport = gui_document.activeView()
    if viewport is None:
        raise RuntimeError(f"No 3D view for document: {document_name}")
    camera = str(viewport.getCamera()) if hasattr(viewport, "getCamera") else ""
    projection = ""
    if camera:
        projection = "Perspective" if "PerspectiveCamera" in camera else "Orthographic"
    viewport_width, viewport_height = _viewport_size(viewport)
    return {
        "active_document": str(document_name),
        "active_view": _view_name(viewport),
        "active_workbench": _workbench_name(gui_module),
        "edit_focus": _edit_focus(gui_document),
        "active_body": _active_body(viewport),
        "camera": camera,
        "projection": projection,
        "viewport_width": viewport_width,
        "viewport_height": viewport_height,
    }


__all__ = ["capture_baseline"]
