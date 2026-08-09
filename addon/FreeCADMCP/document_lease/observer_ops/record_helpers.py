"""Lease record field extraction for observer notifications."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def record_state(record: Any) -> str:
    if isinstance(record, Mapping):
        lease = record.get("lease")
        value = (
            lease.get("state", "")
            if isinstance(lease, Mapping)
            else record.get("state", "")
        )
    else:
        value = getattr(record, "state", "")
    return str(getattr(value, "value", value) or "")


def record_generation(record: Any) -> int | None:
    if isinstance(record, Mapping):
        value = record.get("generation")
    else:
        value = getattr(record, "generation", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def has_accepted_baseline(record: Any) -> bool:
    if not isinstance(record, Mapping):
        return False
    document_state = record.get("document_state")
    if not isinstance(document_state, Mapping):
        return False
    baseline = document_state.get("baseline")
    return isinstance(baseline, Mapping) and bool(baseline.get("sha256"))
