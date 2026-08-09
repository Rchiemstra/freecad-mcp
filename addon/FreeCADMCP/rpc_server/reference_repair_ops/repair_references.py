"""Atomic replacement of broken link properties."""

from __future__ import annotations

import contextlib
from typing import Any

import FreeCAD

try:
    from document_state import document_modified_state
except ImportError:
    from addon.FreeCADMCP.document_state import document_modified_state

from .link_helpers import is_link_property, property_type
from .serialize_property import serialize_property


def _validate_subelement_reference(target: Any, subelement: str) -> None:
    from .. import reference_repair

    reference_repair.validate_subelement_reference(target, subelement)


def resolve_target(owner_doc: Any, reference: dict[str, Any]) -> Any:
    document_name = str(reference.get("document") or owner_doc.Name)
    target_doc = FreeCAD.getDocument(document_name)
    if target_doc is None:
        raise ValueError(f"Target document '{document_name}' is not open")
    object_name = reference.get("object")
    if not object_name:
        raise ValueError("Reference is missing its 'object' name")
    target = target_doc.getObject(str(object_name))
    if target is None:
        raise ValueError(
            f"Target object '{object_name}' not found in document '{document_name}'"
        )
    return target


def resolve_references(
    owner_doc: Any,
    raw_references: Any,
    *,
    validate: bool,
) -> list[tuple[Any, tuple[str, ...]]]:
    if not isinstance(raw_references, list):
        raise ValueError("'references' must be a list")
    resolved = []
    for raw in raw_references:
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid reference entry: {raw!r}")
        target = resolve_target(owner_doc, raw)
        raw_subelements = raw.get("subelements", [])
        if isinstance(raw_subelements, str):
            subelements = (raw_subelements,) if raw_subelements else ()
        elif isinstance(raw_subelements, (list, tuple)):
            subelements = tuple(str(item) for item in raw_subelements if str(item))
        else:
            raise ValueError("'subelements' must be a string or list of strings")
        if validate:
            for subelement in subelements:
                _validate_subelement_reference(target, subelement)
        resolved.append((target, subelements))
    return resolved


def assignment_value(prop_type: str, references: list[tuple[Any, tuple[str, ...]]]) -> Any:
    """Build the native value expected by each FreeCAD link property family."""
    if "LinkSubList" in prop_type:
        return [(target, subelements) for target, subelements in references]
    if "LinkSub" in prop_type:
        if not references:
            return None
        if len(references) != 1:
            raise ValueError(f"{prop_type} accepts exactly one reference")
        target, subelements = references[0]
        return (target, subelements)
    if "LinkList" in prop_type:
        return [target for target, _subelements in references]
    if "Link" in prop_type:
        if not references:
            return None
        if len(references) != 1:
            raise ValueError(f"{prop_type} accepts exactly one reference")
        target, subelements = references[0]
        if subelements:
            raise ValueError(f"{prop_type} does not accept subelements")
        return target
    raise ValueError(f"Unsupported link property type '{prop_type}'")


def recompute_result(doc: Any, requested: bool) -> dict[str, Any]:
    if not requested:
        return {"requested": False, "ok": None, "deferred": True}
    try:
        result = doc.recompute()
        return {"requested": True, "ok": result is not False, "result": result}
    except Exception as exc:
        return {"requested": True, "ok": False, "error": str(exc)}


def _preflight_repairs(
    doc: Any,
    repairs: list[dict[str, Any]],
    *,
    validate: bool,
) -> tuple[list[tuple[Any, str, str, Any]] | None, dict[str, Any] | None]:
    prepared = []
    try:
        for index, repair in enumerate(repairs):
            if not isinstance(repair, dict):
                raise ValueError(f"Repair {index} must be an object")
            object_name = repair.get("object")
            property_name = repair.get("property")
            if not object_name or not property_name:
                raise ValueError(f"Repair {index} requires 'object' and 'property'")
            owner = doc.getObject(str(object_name))
            if owner is None:
                raise ValueError(f"Owner object '{object_name}' not found")
            if property_name not in getattr(owner, "PropertiesList", []):
                raise ValueError(
                    f"Object '{object_name}' has no property '{property_name}'"
                )
            prop_type = property_type(owner, str(property_name))
            if not is_link_property(prop_type):
                raise ValueError(
                    f"{object_name}.{property_name} is not a link property ({prop_type})"
                )
            references = resolve_references(
                doc, repair.get("references"), validate=validate
            )
            value = assignment_value(prop_type, references)
            prepared.append((owner, str(property_name), prop_type, value))
    except Exception as exc:
        return None, {
            "ok": False,
            "repair_committed": False,
            "error": f"Repair preflight failed: {exc}",
        }
    return prepared, None


def _commit_repairs(
    doc: Any,
    prepared: list[tuple[Any, str, str, Any]],
) -> dict[str, Any] | None:
    opened_transaction = False
    try:
        if hasattr(doc, "openTransaction"):
            doc.openTransaction("MCP repair broken references")
            opened_transaction = True
        for owner, property_name, _prop_type, value in prepared:
            setattr(owner, property_name, value)
        if opened_transaction:
            doc.commitTransaction()
    except Exception as exc:
        if opened_transaction:
            with contextlib.suppress(Exception):
                doc.abortTransaction()
        return {
            "ok": False,
            "repair_committed": False,
            "error": f"Repair assignment failed and was rolled back: {exc}",
        }
    return None


def repair_references_gui(
    document_name: str,
    repairs: list[dict[str, Any]],
    *,
    recompute: bool = False,
    validate: bool = False,
) -> dict[str, Any]:
    """Atomically replace complete link properties, with recompute deferred by default."""
    doc = FreeCAD.getDocument(document_name)
    if doc is None:
        return {"ok": False, "error": f"Document '{document_name}' not found"}
    if not isinstance(repairs, list) or not repairs:
        return {"ok": False, "error": "At least one repair is required"}

    prepared, preflight_error = _preflight_repairs(doc, repairs, validate=validate)
    if preflight_error is not None:
        return preflight_error

    commit_error = _commit_repairs(doc, prepared)
    if commit_error is not None:
        return commit_error

    applied = [
        {
            "object": owner.Name,
            "property": property_name,
            "property_type": prop_type,
        }
        for owner, property_name, prop_type, _value in prepared
    ]
    verified_properties = [
        serialize_property(owner, property_name, validate)
        for owner, property_name, _prop_type, _value in prepared
    ]
    remaining_invalid = [
        item for item in verified_properties if item["valid"] is False
    ]
    recompute_status = recompute_result(doc, recompute)
    return {
        "ok": not remaining_invalid,
        "document": document_name,
        "repair_committed": True,
        "applied": applied,
        "recompute": recompute_status,
        "remaining_invalid_repaired_properties": remaining_invalid,
        "validation_performed": validate,
        "modified": document_modified_state(doc),
    }
