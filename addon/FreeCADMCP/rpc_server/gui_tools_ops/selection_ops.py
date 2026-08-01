"""GUI selection operations."""

from __future__ import annotations

from typing import Any

import FreeCAD
import FreeCADGui

from ..gui_dispatch import _flush_gui_events
from .selection_parse import parse_selection_entry


def select_subshapes(
    doc_name: str,
    selections: list[dict[str, Any]] | list[str],
    clear: bool = True,
) -> dict[str, Any]:
    """Select whole objects or sub-shapes (``FaceN`` / ``EdgeN`` / ``VertexN``).

    ``selections`` entries may be:
      - ``"Box"`` or ``"Box:Face1"``
      - ``{"object": "Box", "sub": "Face1"}`` / ``{"obj": ..., "subshape": ...}``
    """
    doc = FreeCAD.getDocument(doc_name)
    if doc is None:
        return {"ok": False, "error": f"Document not found: {doc_name}"}

    if clear:
        FreeCADGui.Selection.clearSelection()

    selected: list[dict[str, str]] = []
    errors: list[str] = []

    for item in selections or []:
        obj_name, sub, parse_error = parse_selection_entry(item)
        if parse_error:
            errors.append(parse_error)
            continue
        if not obj_name:
            errors.append(f"Missing object name in {item!r}")
            continue
        obj = doc.getObject(obj_name)
        if obj is None:
            errors.append(f"Object not found: {obj_name}")
            continue
        try:
            if sub:
                FreeCADGui.Selection.addSelection(doc.Name, obj.Name, sub)
            else:
                FreeCADGui.Selection.addSelection(obj)
            selected.append({"object": obj.Name, "sub": sub})
        except Exception as exc:
            errors.append(f"{obj_name}:{sub or '<obj>'}: {exc}")

    _flush_gui_events()
    return {
        "ok": not errors or bool(selected),
        "selected": selected,
        "errors": errors,
        "count": len(selected),
    }


def get_selection() -> dict[str, Any]:
    items = []
    for sel in FreeCADGui.Selection.getSelectionEx():
        for sub in sel.SubElementNames or [""]:
            items.append(
                {
                    "document": sel.DocumentName,
                    "object": sel.ObjectName,
                    "sub": sub,
                }
            )
    return {"ok": True, "selection": items, "count": len(items)}
