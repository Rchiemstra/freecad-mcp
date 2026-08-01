"""Assign JSON-friendly property dicts onto FreeCAD document objects."""

from __future__ import annotations

from typing import Any

import FreeCAD

try:
    from ..placement_codec import _as_vector, dict_to_placement
except ImportError:  # pragma: no cover - flat addon import path
    from placement_codec import _as_vector, dict_to_placement

from .reference_parsing import resolve_references, to_shape_color


def is_placement_value(value: Any) -> bool:
    return isinstance(value, FreeCAD.Placement)


def assign_link_property(
    doc: FreeCAD.Document,
    obj: FreeCAD.DocumentObject,
    prop: str,
    val: Any,
) -> None:
    ref_obj = doc.getObject(val)
    if ref_obj:
        setattr(obj, prop, ref_obj)
        return
    raise ValueError(f"Referenced object '{val}' not found.")


def assign_document_property(
    doc: FreeCAD.Document,
    obj: FreeCAD.DocumentObject,
    prop: str,
    val: Any,
    current: Any,
) -> bool:
    if is_placement_value(current) and isinstance(val, dict):
        setattr(obj, prop, dict_to_placement(val))
        return True
    if isinstance(current, FreeCAD.Vector) and isinstance(val, dict):
        setattr(obj, prop, _as_vector(val))
        return True
    if prop in ["Base", "Tool", "Source", "Profile"] and isinstance(val, str):
        assign_link_property(doc, obj, prop, val)
        return True
    if prop == "References" and isinstance(val, list):
        setattr(obj, prop, resolve_references(doc, val))
        return True
    return False


def assign_view_property(
    obj: FreeCAD.DocumentObject,
    prop: str,
    val: Any,
) -> bool:
    if prop == "ShapeColor" and isinstance(val, (list, tuple)):
        setattr(obj.ViewObject, prop, to_shape_color(val))
        return True
    if prop == "ViewObject" and isinstance(val, dict):
        for key, item in val.items():
            if key == "ShapeColor":
                setattr(obj.ViewObject, key, to_shape_color(item))
            else:
                setattr(obj.ViewObject, key, item)
        return True
    return False


def assign_single_property(
    doc: FreeCAD.Document,
    obj: FreeCAD.DocumentObject,
    prop: str,
    val: Any,
) -> None:
    if prop in obj.PropertiesList:
        current = getattr(obj, prop)
        if assign_document_property(doc, obj, prop, val, current):
            return
        setattr(obj, prop, val)
        return
    if assign_view_property(obj, prop, val):
        return
    setattr(obj, prop, val)


def set_object_property(
    doc: FreeCAD.Document, obj: FreeCAD.DocumentObject, properties: dict[str, Any]
):
    failures = []
    for prop, val in properties.items():
        try:
            assign_single_property(doc, obj, prop, val)
        except Exception as e:
            FreeCAD.Console.PrintError(f"Property '{prop}' assignment error: {e}\n")
            failures.append(f"{prop}: {e}")

    if failures:
        raise ValueError(
            "Failed to set propert" + ("y" if len(failures) == 1 else "ies")
            + ": " + "; ".join(failures)
        )
