"""Document open and activation on the GUI thread."""

from __future__ import annotations

from typing import Any

import FreeCAD
import FreeCADGui

from ..gui_dispatch import _flush_gui_events


def open_document(path: str) -> dict[str, Any]:
    path = str(path)
    if not path:
        return {"ok": False, "error": "path is required"}
    doc = FreeCAD.openDocument(path)
    if doc is None:
        return {"ok": False, "error": f"Failed to open: {path}"}
    try:
        FreeCAD.setActiveDocument(doc.Name)
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(doc.Name)
    except Exception:
        pass
    _flush_gui_events()
    return {"ok": True, "document": doc.Name, "label": doc.Label, "path": path}


def activate_document(doc_name: str) -> dict[str, Any]:
    doc = FreeCAD.getDocument(doc_name)
    if doc is None:
        return {"ok": False, "error": f"Document not found: {doc_name}"}
    FreeCAD.setActiveDocument(doc.Name)
    try:
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(doc.Name)
    except Exception as exc:
        return {"ok": False, "error": f"Activated App doc but GUI failed: {exc}"}
    _flush_gui_events()
    return {"ok": True, "document": doc.Name, "label": doc.Label}
