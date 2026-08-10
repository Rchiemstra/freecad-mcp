"""Document link manifest collection for snapshot bundles."""

from __future__ import annotations

from typing import Any

import FreeCAD

from ..worker_protocol import ProtocolError, validate_subelement_reference
from ..worker_protocol_ops.subelement_validation import (
    subelement_resolvable_by_freecad_fallback,
)
from .link_helpers import is_link_property, reference_entries


def _tracks_link_property(obj: Any, prop: str, prop_type: str) -> bool:
    return is_link_property(prop_type) or (
        getattr(obj, "TypeId", "") == "App::Link" and prop == "LinkedObject"
    )


def _append_reference_rows(
    *,
    doc: Any,
    obj: Any,
    prop: str,
    prop_type: str,
    refs: list[tuple[Any, list[str]]],
    open_names: set[str],
    links: list[dict[str, Any]],
    broken: list[str],
    invalid_subelements: list[str],
) -> None:
    if (
        getattr(obj, "TypeId", "") == "App::Link"
        and prop == "LinkedObject"
        and not refs
    ):
        broken.append(f"{doc.Name}.{obj.Name}.{prop}")
    for ref_index, (target, subelements) in enumerate(refs):
        target_doc = getattr(getattr(target, "Document", None), "Name", None)
        target_name = getattr(target, "Name", None)
        if (
            not target_doc
            or target_doc not in open_names
            or not target_name
            or FreeCAD.getDocument(target_doc).getObject(target_name) is None
        ):
            broken.append(f"{doc.Name}.{obj.Name}.{prop}")
            continue
        for subelement in subelements:
            try:
                validate_subelement_reference(target, subelement)
            except ProtocolError:
                # FreeCAD may still resolve stale element-map names via
                # getSubObject / Shape.getElement even when indexed names fail.
                if subelement_resolvable_by_freecad_fallback(target, subelement):
                    continue
                invalid_subelements.append(
                    f"{target_doc}.{target_name}.{subelement}"
                )
        links.append({
            "owner_document": doc.Name,
            "owner_object": obj.Name,
            "property": prop,
            "property_type": prop_type,
            "target_document": target_doc,
            "target_object": target_name,
            "subelements": subelements,
            "reference_index": ref_index,
        })


def collect_link_manifest(
    documents: list[Any],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    links: list[dict[str, Any]] = []
    broken: list[str] = []
    invalid_subelements: list[str] = []
    open_names = set(FreeCAD.listDocuments().keys())
    for doc in documents:
        for obj in doc.Objects:
            for prop in getattr(obj, "PropertiesList", []):
                try:
                    prop_type = obj.getTypeIdOfProperty(prop)
                except Exception:
                    continue
                if not _tracks_link_property(obj, prop, prop_type):
                    continue
                try:
                    value = getattr(obj, prop)
                except Exception:
                    continue
                _append_reference_rows(
                    doc=doc,
                    obj=obj,
                    prop=prop,
                    prop_type=prop_type,
                    refs=reference_entries(value),
                    open_names=open_names,
                    links=links,
                    broken=broken,
                    invalid_subelements=invalid_subelements,
                )
    return (
        links,
        sorted(set(broken)),
        sorted(set(invalid_subelements)),
    )
