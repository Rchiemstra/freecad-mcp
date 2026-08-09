"""Load post-recompute property references for link validation."""

from __future__ import annotations

import FreeCAD

from ..worker_entry_types.external_link_unresolved import ExternalLinkUnresolved
from .link_validation_helpers import (
    _normalize_reference_entries_for_property,
    _property_type_for_key,
)
from .reference_entries import reference_entries


def load_post_property_state(
    property_key: tuple[str, str, str],
    snapshot: dict,
) -> tuple[list, str]:
    key = property_key
    label = f"{key[0]}.{key[1]}.{key[2]}"
    try:
        owner_doc = FreeCAD.getDocument(key[0])
    except Exception:
        owner_doc = None
    if owner_doc is None:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    owner = owner_doc.getObject(key[1])
    if owner is None:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    properties = getattr(owner, "PropertiesList", None)
    if not properties or key[2] not in properties:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    try:
        refs = reference_entries(getattr(owner, key[2]))
    except Exception as exc:
        raise ExternalLinkUnresolved(
            f"Snapshot links did not resolve: {label}"
        ) from exc
    property_type = _property_type_for_key(snapshot, key)
    refs = _normalize_reference_entries_for_property(
        refs, property_type=property_type, label=label
    )
    return refs, label
