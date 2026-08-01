"""Two-phase expected-link validation for isolated worker snapshots."""

from __future__ import annotations

from ..worker_entry_types.external_link_unresolved import ExternalLinkUnresolved
from ..worker_protocol_ops.job_validation import validate_snapshot_manifest
from .link_validation_helpers import (
    _expected_rows_by_reference_index,
    _group_expected_link_entries,
    _ignored_links_for_property,
    _live_subelements_match_warn_policy,
    _manifest_identity,
    _normalize_reference_entries_for_property,
    _property_keys_in_snapshot,
    _property_type_for_key,
    _reference_identity,
    _require_claimed_ignored_subelements_unresolvable,
    _validate_ignored_reference_pre_recompute,
)


def _validate_property_group_pre_recompute(
    expected_rows: list[dict],
    snapshot: dict,
    *,
    property_key: tuple[str, str, str],
) -> list[dict]:
    """Phase 1 for one property: exact-order reopen fidelity with warn-policy exemptions."""
    try:
        from ..worker_entry import _read_property_reference_entries
    except ImportError:
        from .link_validation_helpers import _read_property_reference_entries

    key = property_key
    refs, label = _read_property_reference_entries(key[0], key[1], key[2])
    property_type = _property_type_for_key(snapshot, key)
    refs = _normalize_reference_entries_for_property(
        refs, property_type=property_type, label=label
    )
    ignored_by_index = _ignored_links_for_property(snapshot, key)
    expected_by_ref = _expected_rows_by_reference_index(expected_rows)
    anchors: list[dict] = []
    for ref_index, (target, subelements) in enumerate(refs):
        ignored = ignored_by_index.get(ref_index)
        expected = expected_by_ref.pop(ref_index, None)
        if ignored is not None and expected is not None:
            kept_subs = [str(item) for item in expected.get("subelements", [])]
            ignored_subs = [str(item) for item in ignored.get("subelements", [])]
            if (
                target.Document.Name != expected["target_document"]
                or target.Name != expected["target_object"]
                or target.Document.Name != ignored["target_document"]
                or target.Name != ignored["target_object"]
                or not _live_subelements_match_warn_policy(
                    subelements, kept_subs, ignored_subs
                )
            ):
                raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
            _require_claimed_ignored_subelements_unresolvable(
                target, ignored_subs, label
            )
            anchors.append(
                {"expected": expected, "ignored": ignored, "ref_index": ref_index}
            )
            continue
        if ignored is not None:
            _validate_ignored_reference_pre_recompute(
                ignored, target, subelements, label
            )
            anchors.append({"ignored": ignored, "ref_index": ref_index})
            continue
        if expected is None:
            raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
        if _reference_identity(target, subelements) != _manifest_identity(expected):
            raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
        anchors.append({"expected": expected, "ref_index": ref_index})
    if expected_by_ref:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    return anchors


def _validate_expected_links_pre_recompute(snapshot) -> list[dict]:
    """Phase 1: per-property exact-order reopen fidelity before any document recompute."""
    validate_snapshot_manifest(snapshot)
    anchors: list[dict] = []
    expected_map = dict(_group_expected_link_entries(snapshot.get("expected_links", [])))
    for key in _property_keys_in_snapshot(snapshot):
        anchors.extend(
            _validate_property_group_pre_recompute(
                expected_map.get(key, []), snapshot, property_key=key
            )
        )
    return anchors
