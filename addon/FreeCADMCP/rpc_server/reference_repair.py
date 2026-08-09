"""Recovery-safe inspection and repair of FreeCAD link properties.

These helpers intentionally do not serialize owner shapes and do not recompute by
default.  A document with a stale ``EdgeNNN``/``FaceNNN`` reference can therefore
have all of its link properties repaired before FreeCAD evaluates dependants.
"""

from __future__ import annotations

from typing import Any

import FreeCAD

from .worker_protocol import validate_subelement_reference

try:
    from document_state import document_modified_state
except ImportError:
    from addon.FreeCADMCP.document_state import document_modified_state


def _is_link_property(prop_type: str) -> bool:
    return "PropertyLink" in prop_type or "PropertyXLink" in prop_type


def _reference_entries(value: Any) -> list[tuple[Any, list[str]]]:
    """Return ordered ``(target, subelements)`` entries without reading shapes."""
    if hasattr(value, "Document") and hasattr(value, "Name"):
        return [(value, [])]
    if isinstance(value, tuple) and value:
        target = value[0]
        if hasattr(target, "Document") and hasattr(target, "Name"):
            subelements: list[str] = []
            for item in value[1:]:
                if isinstance(item, str):
                    if item:
                        subelements.append(item)
                elif isinstance(item, (list, tuple)):
                    subelements.extend(str(sub) for sub in item if str(sub))
            return [(target, subelements)]
    if isinstance(value, (list, tuple)):
        result: list[tuple[Any, list[str]]] = []
        for item in value:
            result.extend(_reference_entries(item))
        return result
    return []


def _property_type(obj: Any, property_name: str) -> str:
    for method_name in ("getTypeIdOfProperty", "getTypeOfProperty"):
        method = getattr(obj, method_name, None)
        if callable(method):
            try:
                return str(method(property_name))
            except Exception:
                pass
    return ""


def _serialize_property(owner: Any, property_name: str, validate: bool) -> dict[str, Any]:
    prop_type = _property_type(owner, property_name)
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

    for target, subelements in _reference_entries(value):
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
                    validate_subelement_reference(target, subelement)
                except Exception as exc:
                    ref["valid"] = False
                    ref["errors"].append(str(exc))
        if ref["valid"] is False:
            entry["valid"] = False
            entry["errors"].extend(ref["errors"])
        entry["references"].append(ref)
    return entry


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
            prop_type = _property_type(obj, property_name)
            is_app_link = getattr(obj, "TypeId", "") == "App::Link" and property_name == "LinkedObject"
            if not _is_link_property(prop_type) and not is_app_link:
                continue
            item = _serialize_property(obj, property_name, validate)
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


def _resolve_target(owner_doc: Any, reference: dict[str, Any]) -> Any:
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


def _resolve_references(
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
        target = _resolve_target(owner_doc, raw)
        raw_subelements = raw.get("subelements", [])
        if isinstance(raw_subelements, str):
            subelements = (raw_subelements,) if raw_subelements else ()
        elif isinstance(raw_subelements, (list, tuple)):
            subelements = tuple(str(item) for item in raw_subelements if str(item))
        else:
            raise ValueError("'subelements' must be a string or list of strings")
        if validate:
            for subelement in subelements:
                validate_subelement_reference(target, subelement)
        resolved.append((target, subelements))
    return resolved


def _assignment_value(prop_type: str, references: list[tuple[Any, tuple[str, ...]]]) -> Any:
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


def _recompute_result(doc: Any, requested: bool) -> dict[str, Any]:
    if not requested:
        return {"requested": False, "ok": None, "deferred": True}
    try:
        result = doc.recompute()
        return {"requested": True, "ok": result is not False, "result": result}
    except Exception as exc:
        return {"requested": True, "ok": False, "error": str(exc)}


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
            prop_type = _property_type(owner, str(property_name))
            if not _is_link_property(prop_type):
                raise ValueError(
                    f"{object_name}.{property_name} is not a link property ({prop_type})"
                )
            references = _resolve_references(
                doc, repair.get("references"), validate=validate
            )
            value = _assignment_value(prop_type, references)
            prepared.append((owner, str(property_name), prop_type, value))
    except Exception as exc:
        return {
            "ok": False,
            "repair_committed": False,
            "error": f"Repair preflight failed: {exc}",
        }

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
            try:
                doc.abortTransaction()
            except Exception:
                pass
        return {
            "ok": False,
            "repair_committed": False,
            "error": f"Repair assignment failed and was rolled back: {exc}",
        }

    applied = [
        {
            "object": owner.Name,
            "property": property_name,
            "property_type": prop_type,
        }
        for owner, property_name, prop_type, _value in prepared
    ]
    verified_properties = [
        _serialize_property(owner, property_name, validate)
        for owner, property_name, _prop_type, _value in prepared
    ]
    remaining_invalid = [
        item for item in verified_properties if item["valid"] is False
    ]
    recompute_status = _recompute_result(doc, recompute)
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
