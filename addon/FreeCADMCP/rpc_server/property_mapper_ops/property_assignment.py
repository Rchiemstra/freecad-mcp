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


def _property_type(obj: FreeCAD.DocumentObject, prop: str) -> str | None:
    getter = getattr(obj, "getTypeIdOfProperty", None)
    return getter(prop) if callable(getter) else None


def refuse_shown_array_layout(obj: FreeCAD.DocumentObject, prop: str) -> None:
    """Refuse a PlacementList that would not move an array's existing element objects.

    FreeCAD lays an App::Link array out from PlacementList only while ShowElement is false,
    or when the list is set before ElementCount creates the elements. Afterwards the list keeps
    the new value but the elements, and so the geometry, stay where they were.
    """
    elements = list(getattr(obj, "ElementList", None) or [])
    if prop != "PlacementList" or getattr(obj, "ShowElement", False) is not True or not elements:
        return
    raise ValueError(
        f"PlacementList would not move the {len(elements)} existing elements of this Link "
        "array while ShowElement is true; set ShowElement to false before PlacementList in "
        "the same call, set PlacementList before ElementCount, or edit each element's Placement"
    )


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
    if isinstance(val, list) and _property_type(obj, prop) == "App::PropertyPlacementList":
        refuse_shown_array_layout(obj, prop)
        setattr(obj, prop, [dict_to_placement(v) if isinstance(v, dict) else v for v in val])
        return True
    if isinstance(current, FreeCAD.Vector) and isinstance(val, dict):
        setattr(obj, prop, _as_vector(val))
        return True
    if (
        isinstance(val, str)
        and obj.getTypeIdOfProperty(prop) in {"App::PropertyLink", "App::PropertyXLink"}
    ):
        assign_link_property(doc, obj, prop, val)
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
