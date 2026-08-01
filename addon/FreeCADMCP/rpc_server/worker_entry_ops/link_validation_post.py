"""Two-phase expected-link validation for isolated worker snapshots."""

from __future__ import annotations

from ..worker_entry_types.external_link_unresolved import ExternalLinkUnresolved
from ..worker_entry_types.external_subelement_unresolved import ExternalSubelementUnresolved
from .link_validation_helpers import (
    _anchor_property_key,
    _ignored_links_for_property,
    _property_keys_in_snapshot,
    _validate_authenticated_ignored_post_recompute,
)
from .link_validation_post_load import load_post_property_state
from .link_validation_post_rows import (
    validate_post_expected_only_row,
    validate_post_ignored_and_expected_row,
)


def _validate_property_group_post_recompute(
    anchors_for_property: list[dict],
    snapshot: dict,
    *,
    property_key: tuple[str, str, str],
) -> list[str]:
    """Phase 2 for one property: same entry count/order, target identity, subelement resolution.

    Post-recompute topological renaming is accepted only as same-index subelement name
    changes on the same target object that still pass ``validate_subelement_reference``.
    This does not prove persistent-topology equivalence for arbitrary valid faces.
    LinkSubList entry reordering is rejected because indices must still match the manifest.
    """
    key = property_key
    refs, label = load_post_property_state(key, snapshot)
    authenticated_ignored_by_ref = {
        int(anchor["ref_index"]): anchor["ignored"]
        for anchor in anchors_for_property
        if anchor.get("ignored") is not None
    }
    expected_by_ref = {
        int(anchor["ref_index"]): anchor["expected"]
        for anchor in anchors_for_property
        if anchor.get("expected") is not None
    }
    warnings: list[str] = []
    missing_subelements: list[str] = []
    for ref_index, (target, subelements) in enumerate(refs):
        expected = expected_by_ref.pop(ref_index, None)
        ignored = authenticated_ignored_by_ref.pop(ref_index, None)
        if ignored is not None and expected is not None:
            validate_post_ignored_and_expected_row(
                expected=expected,
                ignored=ignored,
                target=target,
                subelements=subelements,
                label=label,
                warnings=warnings,
                missing_subelements=missing_subelements,
            )
            continue
        if ignored is not None:
            _validate_authenticated_ignored_post_recompute(
                ignored, target, subelements, label
            )
            continue
        if expected is None:
            raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
        validate_post_expected_only_row(
            expected=expected,
            target=target,
            subelements=subelements,
            label=label,
            warnings=warnings,
            missing_subelements=missing_subelements,
        )
    if expected_by_ref or authenticated_ignored_by_ref:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    if missing_subelements:
        raise ExternalSubelementUnresolved(
            "Snapshot subelements did not resolve: "
            + ", ".join(sorted(set(missing_subelements)))
        )
    return warnings


def _attach_link_warnings(result: dict, link_validation_warnings: list[str]) -> None:
    if not link_validation_warnings:
        return
    result["link_warnings"] = list(link_validation_warnings)
    session = dict(result.get("session") or {})
    session["link_warnings"] = list(link_validation_warnings)
    result["session"] = session


def _validate_expected_links_post_recompute(anchors: list[dict], snapshot: dict) -> list[str]:
    warnings: list[str] = []
    anchors_by_property: dict[tuple[str, str, str], list[dict]] = {}
    for anchor in anchors:
        key = _anchor_property_key(anchor)
        anchors_by_property.setdefault(key, []).append(anchor)
    for key in _property_keys_in_snapshot(snapshot):
        property_anchors = anchors_by_property.get(key, [])
        if not property_anchors and not _ignored_links_for_property(snapshot, key):
            continue
        warnings.extend(
            _validate_property_group_post_recompute(
                property_anchors, snapshot, property_key=key
            )
        )
    return warnings
