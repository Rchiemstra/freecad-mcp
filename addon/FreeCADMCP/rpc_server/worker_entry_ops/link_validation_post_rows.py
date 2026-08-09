"""Per-reference post-recompute validation rows for worker link checks."""

from __future__ import annotations

from ..worker_entry_types.external_link_unresolved import ExternalLinkUnresolved
from ..worker_protocol_ops.subelement_validation import validate_subelement_reference
from .link_validation_helpers import (
    _current_kept_subelements_post_recompute,
    _expected_link_label,
    _validate_authenticated_ignored_post_recompute,
)


def validate_post_ignored_and_expected_row(
    *,
    expected: dict,
    ignored: dict,
    target,
    subelements,
    label: str,
    warnings: list[str],
    missing_subelements: list[str],
) -> None:
    kept_subs = [str(item) for item in expected.get("subelements", [])]
    ignored_subs = [str(item) for item in ignored.get("subelements", [])]
    if (
        target.Document.Name != expected["target_document"]
        or target.Name != expected["target_object"]
    ):
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    _validate_authenticated_ignored_post_recompute(
        ignored,
        target,
        subelements,
        label,
        kept_subs=kept_subs,
    )
    current_kept_subs = _current_kept_subelements_post_recompute(subelements, ignored_subs)
    if current_kept_subs is None:
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    entry_label = _expected_link_label(expected)
    for subelement in current_kept_subs:
        try:
            validate_subelement_reference(target, subelement)
        except Exception as exc:
            missing_subelements.append(str(exc))
    if len(current_kept_subs) != len(kept_subs):
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {entry_label}")
    if current_kept_subs != kept_subs:
        remap = ", ".join(
            f"{before} -> {after}"
            for before, after in zip(kept_subs, current_kept_subs, strict=False)
        )
        warnings.append(f"subelement_remapped:{entry_label}: {remap}")


def validate_post_expected_only_row(
    *,
    expected: dict,
    target,
    subelements,
    label: str,
    warnings: list[str],
    missing_subelements: list[str],
) -> None:
    entry_label = _expected_link_label(expected)
    if (
        target.Document.Name != expected["target_document"]
        or target.Name != expected["target_object"]
    ):
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {label}")
    expected_subs = [str(item) for item in expected.get("subelements", [])]
    current_subs = [str(item) for item in subelements]
    entry_subelement_errors: list[str] = []
    for subelement in current_subs:
        try:
            validate_subelement_reference(target, subelement)
        except Exception as exc:
            entry_subelement_errors.append(str(exc))
    if entry_subelement_errors:
        missing_subelements.extend(entry_subelement_errors)
        return
    if len(current_subs) != len(expected_subs):
        raise ExternalLinkUnresolved(f"Snapshot links did not resolve: {entry_label}")
    if current_subs != expected_subs:
        remap = ", ".join(
            f"{before} -> {after}"
            for before, after in zip(expected_subs, current_subs, strict=False)
        )
        warnings.append(f"subelement_remapped:{entry_label}: {remap}")
