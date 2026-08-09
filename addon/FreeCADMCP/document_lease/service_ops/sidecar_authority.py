"""Document lease service operations — sidecar authority."""

from __future__ import annotations

from pathlib import Path

from ..errors.coordination_error import CoordinationError
from ..model import (
    LeaseRecord,
)
from ..sidecar import (
    SidecarError,
    sidecar_path_for,
)


def _sidecar_path(record: LeaseRecord) -> Path | None:
    if not record.document.canonical_path:
        return None
    return sidecar_path_for(record.document.canonical_path)


def _authority_equal(left: LeaseRecord, right: LeaseRecord) -> bool:
    return (
        left.lease_id == right.lease_id
        and left.generation == right.generation
        and left.token_fingerprint == right.token_fingerprint
        and left.record_revision == right.record_revision
        and left.state == right.state
        and left.state_revision == right.state_revision
        and left.document.session_uuid == right.document.session_uuid
        and left.document.comparison_key == right.document.comparison_key
        and left.migration == right.migration
    )


def _assert_sidecar_matches(self, record: LeaseRecord) -> None:
    path = self._sidecar_path(record)
    if path is None:
        return
    try:
        persisted = self.sidecar_store.read(path)
    except SidecarError as exc:
        raise CoordinationError(
            f"document sidecar is unavailable or invalid: {exc}"
        ) from exc
    if not self._authority_equal(record, persisted):
        raise CoordinationError("registry and sidecar authority do not match")
