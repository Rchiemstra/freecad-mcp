"""Two-phase expected-link validation for isolated worker snapshots."""

from __future__ import annotations

from ..worker_entry_types.external_link_unresolved import ExternalLinkUnresolved
from ..worker_protocol_ops.subelement_validation import validate_subelement_reference
from .reference_entries import reference_entries


def _expected_link_label(expected: dict) -> str:
    return (
        f"{expected['owner_document']}.{expected['owner_object']}.{expected['property']}"
    )


def _property_group_key(expected: dict) -> tuple[str, str, str]:
    return (
        expected["owner_document"],
        expected["owner_object"],
        expected["property"],
    )


def _manifest_identity(expected: dict) -> tuple[str, str, tuple[str, ...]]:
    return (
        expected["target_document"],
        expected["target_object"],
        tuple(str(item) for item in expected.get("subelements", [])),
    )


def _reference_identity(target, subelements) -> tuple[str, str, tuple[str, ...]]:
    return (
        target.Document.Name,
        target.Name,
        tuple(str(item) for item in subelements),
    )


def _group_expected_link_entries(
    entries: list[dict],
) -> list[tuple[tuple[str, str, str], list[dict]]]:
    """Group manifest rows by owner property while preserving manifest order."""
    groups: dict[tuple[str, str, str], list[dict]] = {}
    order: list[tuple[str, str, str]] = []
    for entry in entries:
        key = _property_group_key(entry)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(entry)
    return [(key, groups[key]) for key in order]


def _read_property_reference_entries(
    owner_document: str,
    owner_object: str,
    property_name: str,
) -> tuple[list[tuple], str]:
    """Return parsed reference entries for one owner property or raise via label."""
    try:
        from ..worker_entry import FreeCAD
    except ImportError:
        import FreeCAD

    label = f"{owner_document}.{owner_object}.{property_name}"
    try:
        owner_doc = FreeCAD.getDocument(owner_document)
    except Exception:
        owner_doc = None
    if owner_doc is None:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    owner = owner_doc.getObject(owner_object)
    if owner is None:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    properties = getattr(owner, "PropertiesList", None)
    if not properties or property_name not in properties:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    try:
        return reference_entries(getattr(owner, property_name)), label
    except Exception as exc:
        raise ExternalLinkUnresolved(
            f"Snapshot links did not resolve: {label}"
        ) from exc


def _ignored_links_for_property(
    snapshot: dict,
    key: tuple[str, str, str],
) -> dict[int, dict]:
    ignored: dict[int, dict] = {}
    for entry in snapshot.get("ignored_links") or []:
        entry_key = (
            entry["owner_document"],
            entry["owner_object"],
            entry["property"],
        )
        if entry_key != key:
            continue
        index = int(entry["reference_index"])
        if index in ignored:
            raise ExternalLinkUnresolved(
                f"Snapshot links did not resolve: {key[0]}.{key[1]}.{key[2]}"
            )
        ignored[index] = entry
    return ignored


def _live_subelements_match_warn_policy(
    live_subs,
    kept_subs: list[str],
    ignored_subs: list[str],
) -> bool:
    live = [str(item) for item in live_subs]
    kept = [str(item) for item in kept_subs]
    ignored = [str(item) for item in ignored_subs]
    if len(live) != len(kept) + len(ignored):
        return False
    if [item for item in live if item in set(kept)] != kept:
        return False
    if [item for item in live if item in set(ignored)] != ignored:
        return False
    return set(live) == set(kept) | set(ignored)


def _current_kept_subelements_post_recompute(
    live_subs,
    ignored_subs: list[str],
) -> list[str] | None:
    """Live subs with warn-policy ignored subs removed (multiset, first occurrence)."""
    remaining = [str(item) for item in live_subs]
    for ign in ignored_subs:
        if ign not in remaining:
            return None
        remaining.remove(ign)
    return remaining


def _property_type_for_key(
    snapshot: dict,
    key: tuple[str, str, str],
) -> str:
    for source in (snapshot.get("expected_links") or [], snapshot.get("ignored_links") or []):
        for entry in source:
            if _property_group_key(entry) == key:
                return str(entry.get("property_type") or "")
    return ""


def _is_single_linksub_property(property_type: str) -> bool:
    return bool(property_type) and "LinkSub" in property_type and "LinkSubList" not in property_type


def _normalize_reference_entries_for_property(
    refs: list[tuple],
    *,
    property_type: str,
    label: str,
) -> list[tuple]:
    """Collapse accidental per-subelement splits on single-target LinkSub properties."""
    if not refs or not _is_single_linksub_property(property_type) or len(refs) == 1:
        return refs
    target_doc = refs[0][0].Document.Name
    target_name = refs[0][0].Name
    subs: list[str] = []
    for target, subelements in refs:
        if target.Document.Name != target_doc or target.Name != target_name:
            raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
        subs.extend(str(item) for item in subelements)
    return [(refs[0][0], subs)]


def _expected_rows_by_reference_index(rows: list[dict]) -> dict[int, dict]:
    indexed: dict[int, dict] = {}
    for offset, row in enumerate(rows):
        index = int(row["reference_index"]) if "reference_index" in row else offset
        if index in indexed:
            raise ExternalLinkUnresolved(
                f"Snapshot links did not resolve: duplicate reference_index {index}"
            )
        indexed[index] = row
    return indexed


def _require_claimed_ignored_subelements_unresolvable(
    target,
    ignored_subs: list[str],
    label: str,
) -> None:
    """Reject ignored metadata that exempts subelements still valid on reopen."""
    for subelement in ignored_subs:
        try:
            validate_subelement_reference(target, subelement)
        except Exception:
            continue
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")


def _ignored_subelements_from_entry(ignored: dict) -> list[str]:
    ignored_subs = [str(item) for item in ignored.get("subelements", [])]
    if not ignored_subs:
        raise ExternalLinkUnresolved("Snapshot links did not resolve")
    return ignored_subs


def _validate_ignored_target_identity(ignored: dict, target, label: str) -> None:
    if (
        target.Document.Name != ignored["target_document"]
        or target.Name != ignored["target_object"]
    ):
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")


def _validate_ignored_reference_pre_recompute(
    ignored: dict,
    target,
    subelements,
    label: str,
) -> None:
    """Phase 1: authenticate warn-policy ignored metadata on reopen."""
    _validate_ignored_target_identity(ignored, target, label)
    ignored_subs = _ignored_subelements_from_entry(ignored)
    if not _live_subelements_match_warn_policy(subelements, [], ignored_subs):
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    _require_claimed_ignored_subelements_unresolvable(target, ignored_subs, label)


def _ignored_subelements_present_in_live(live_subs, ignored_subs: list[str]) -> bool:
    remaining = [str(item) for item in live_subs]
    for ign in ignored_subs:
        if ign not in remaining:
            return False
        remaining.remove(ign)
    return True


def _validate_authenticated_ignored_post_recompute(
    ignored: dict,
    target,
    subelements,
    label: str,
    *,
    kept_subs: list[str] | None = None,
) -> None:
    """Phase 2: structural fidelity for Phase-1-authenticated ignored occurrences."""
    _validate_ignored_target_identity(ignored, target, label)
    ignored_subs = _ignored_subelements_from_entry(ignored)
    kept = [str(item) for item in (kept_subs or [])]
    live = [str(item) for item in subelements]
    if not _ignored_subelements_present_in_live(live, ignored_subs):
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    if not kept:
        if live != ignored_subs:
            raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
        return
    if len(live) != len(kept) + len(ignored_subs):
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")


def _anchor_property_key(anchor: dict) -> tuple[str, str, str]:
    source = anchor.get("expected") or anchor.get("ignored")
    if source is None:
        raise ExternalLinkUnresolved("Snapshot links did not resolve")
    return _property_group_key(source)


def _recompute_snapshot_documents() -> None:
    try:
        from ..worker_entry import FreeCAD
    except ImportError:
        import FreeCAD

    for doc in FreeCAD.listDocuments().values():
        doc.recompute()


def _property_keys_in_snapshot(snapshot: dict) -> list[tuple[str, str, str]]:
    order: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in list(snapshot.get("expected_links") or []) + list(
        snapshot.get("ignored_links") or []
    ):
        key = _property_group_key(entry)
        if key in seen:
            continue
        seen.add(key)
        order.append(key)
    return order

