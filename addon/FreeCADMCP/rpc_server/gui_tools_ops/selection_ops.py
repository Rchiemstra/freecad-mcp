"""Selection helpers for GUI-thread tools."""

from __future__ import annotations

from typing import Any

import FreeCAD
import FreeCADGui

from ..gui_dispatch import _flush_gui_events
from .selection_parse import parse_selection_entry, subshape_missing


def _selection_failure(
    errors: list[str],
    unknown: list[str],
    *,
    code: str | None = None,
    selected: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if code is None:
        if unknown:
            code = "OBJECT_NOT_FOUND"
        elif any(error.startswith("Subobject not found") for error in errors):
            code = "SUBSHAPE_NOT_FOUND"
        else:
            code = "INVALID_ARGUMENT"
    chosen = [] if selected is None else selected
    return {
        "ok": False,
        "success": False,
        "error_code": code,
        "error": "; ".join(errors),
        "errors": errors,
        "unknown": unknown,
        "selected": chosen,
        "count": len(chosen),
    }


def _resolve_entries(
    doc: Any, selections: list[dict[str, Any]] | list[str]
) -> tuple[list[tuple[Any, str, str]], list[str], list[str]]:
    resolved: list[tuple[Any, str, str]] = []
    errors: list[str] = []
    unknown: list[str] = []
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
            unknown.append(str(obj_name))
            continue
        if sub and subshape_missing(obj, sub):
            errors.append(f"Subobject not found: {obj_name}.{sub}")
            continue
        resolved.append((obj, obj_name, sub))
    return resolved, errors, unknown


def _apply_entries(
    doc: Any, resolved: list[tuple[Any, str, str]]
) -> tuple[list[dict[str, str]], list[str]]:
    selected: list[dict[str, str]] = []
    errors: list[str] = []
    for obj, obj_name, sub in resolved:
        try:
            if sub:
                FreeCADGui.Selection.addSelection(doc.Name, obj.Name, sub)
            else:
                FreeCADGui.Selection.addSelection(obj)
            selected.append({"object": obj.Name, "sub": sub})
        except Exception as exc:
            errors.append(f"{obj_name}:{sub or '<obj>'}: {exc}")
    return selected, errors


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
    try:
        doc = FreeCAD.getDocument(doc_name)
    except NameError:  # getDocument raises for unknown names
        doc = None
    if doc is None:
        return {"ok": False, "error": f"Document not found: {doc_name}"}

    resolved, errors, unknown = _resolve_entries(doc, selections)
    if errors:
        return _selection_failure(errors, unknown)
    if clear:
        FreeCADGui.Selection.clearSelection()
    selected, apply_errors = _apply_entries(doc, resolved)
    if apply_errors:
        return _selection_failure(
            apply_errors, [], code="SELECTION_FAILED", selected=selected
        )
    _flush_gui_events()
    return {
        "ok": True,
        "selected": selected,
        "errors": [],
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


__all__ = ["get_selection", "select_subshapes"]
