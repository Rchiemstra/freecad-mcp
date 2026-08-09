"""Serialize link properties without owner geometry."""

from __future__ import annotations

from typing import Any

from .link_helpers import property_type, reference_entries


def _validate_subelement_reference(target: Any, subelement: str) -> None:
    from .. import reference_repair

    reference_repair.validate_subelement_reference(target, subelement)


def serialize_property(owner: Any, property_name: str, validate: bool) -> dict[str, Any]:
    prop_type = property_type(owner, property_name)
    entry: dict[str, Any] = {
        "object": owner.Name,
        "property": property_name,
        "property_type": prop_type,
        "references": [],
        "valid": True if validate else None,
        "validation_performed": validate,
        "errors": [],
    }
    try:
        value = getattr(owner, property_name)
    except Exception as exc:
        entry["valid"] = False
        entry["errors"].append(f"Property read failed: {exc}")
        return entry

    for target, subelements in reference_entries(value):
        target_document = getattr(getattr(target, "Document", None), "Name", None)
        target_name = getattr(target, "Name", None)
        ref = {
            "document": target_document,
            "object": target_name,
            "subelements": subelements,
            "valid": True if validate else None,
            "validation_performed": validate,
            "errors": [],
        }
        if not target_document or not target_name:
            ref["valid"] = False
            ref["errors"].append("Target document or object is unavailable")
        elif validate:
            for subelement in subelements:
                try:
                    _validate_subelement_reference(target, subelement)
                except Exception as exc:
                    ref["valid"] = False
                    ref["errors"].append(str(exc))
        if ref["valid"] is False:
            entry["valid"] = False
            entry["errors"].extend(ref["errors"])
        entry["references"].append(ref)
    return entry
