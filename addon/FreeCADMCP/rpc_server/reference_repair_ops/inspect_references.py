"""Read-only inspection of document link properties."""

from __future__ import annotations

from typing import Any

import FreeCAD

from .link_helpers import is_link_property, property_type
from .serialize_property import serialize_property


def inspect_references_gui(
    document_name: str,
    object_names: list[str] | None = None,
    *,
    only_invalid: bool = False,
    validate: bool = False,
) -> dict[str, Any]:
    """Inspect links without serializing owner geometry or recomputing the document."""
    doc = FreeCAD.getDocument(document_name)
    if doc is None:
        return {"ok": False, "error": f"Document '{document_name}' not found"}

    if object_names:
        objects = []
        missing = []
        for name in object_names:
            obj = doc.getObject(str(name))
            if obj is None:
                missing.append(str(name))
            else:
                objects.append(obj)
    else:
        objects = list(doc.Objects)
        missing = []

    references: list[dict[str, Any]] = []
    for obj in objects:
        for property_name in getattr(obj, "PropertiesList", []):
            prop_type = property_type(obj, property_name)
            is_app_link = (
                getattr(obj, "TypeId", "") == "App::Link"
                and property_name == "LinkedObject"
            )
            if not is_link_property(prop_type) and not is_app_link:
                continue
            item = serialize_property(obj, property_name, validate)
            if only_invalid and item["valid"] is not False:
                continue
            references.append(item)

    return {
        "ok": not missing,
        "document": document_name,
        "missing_objects": missing,
        "invalid_count": sum(1 for item in references if item["valid"] is False),
        "references": references,
        "validation_performed": validate,
        "recomputed": False,
    }
