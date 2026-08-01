"""Compare-and-swap identity checks for sidecar mutations."""

from __future__ import annotations

from ..model import LeaseRecord


def matches_cas(current: LeaseRecord, expected: LeaseRecord) -> bool:
    return (
        current.lease_id == expected.lease_id
        and current.generation == expected.generation
        and current.token_fingerprint == expected.token_fingerprint
        and current.record_revision == expected.record_revision
        and current.document.session_uuid == expected.document.session_uuid
        and current.migration == expected.migration
    )
