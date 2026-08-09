"""Document lease service operations — queries."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ..errors.coordination_error import CoordinationError
from ..errors.foreign_recovery_error import ForeignRecoveryError
from ..errors.lease_conflict_error import LeaseConflictError
from ..model import (
    DocumentIdentity,
    DocumentSelector,
    FileBaseline,
)
from ..sidecar import (
    sidecar_path_for,
)


def get(
    self, selector: DocumentSelector | Mapping[str, Any] | str
) -> dict[str, Any] | None:
    identity = self.identity_service.resolve(selector)
    with self._lock:
        record = self._records.get(identity.session_uuid)
        return record.to_public_dict() if record else None


def list_records(self) -> list[dict[str, Any]]:
    with self._lock:
        return [record.to_public_dict() for record in self._records.values()]


def has_unresolved_owner(self, mcp_runtime_id: str) -> bool:
    """Return whether an MCP runtime still owns local lease authority.

    The request-id journal uses this conservative process-local predicate
    to retain mutation tombstones for the complete lease/recovery
    lifetime.  Every registry state counts, including acquiring, stale,
    error, user-intervened, and dirty-recovery records; only an exact
    service resolution removes the owner from consideration.
    """

    runtime_id = str(mcp_runtime_id or "")
    if not runtime_id:
        return False
    with self._lock:
        return any(
            record.owner.mcp_instance_id == runtime_id
            for record in self._records.values()
        )


def get_foreign_recovery(
    self, selector: DocumentSelector | Mapping[str, Any] | str
) -> dict[str, Any] | None:
    identity = self.identity_service.resolve(selector)
    with self._lock:
        foreign = self._foreign_records.get(identity.session_uuid)
        return foreign.to_public_dict() if foreign else None


def refresh_orphaned_foreign_document_identity(
    self, *, document: Any
) -> DocumentIdentity:
    """Repair exact-proxy identity drift for a recoverable missing sidecar.

    Registration can detect an identity mismatch before acquisition gets a
    chance to run its full hash. This bounded repair locates only the exact
    previously registered proxy, proves its foreign authority inactive,
    and accepts a refresh only when the on-disk metadata still matches its
    saved baseline. The acquisition path repeats the check with SHA-256
    evidence before publishing new authority. A legacy worker-snapshot
    false-positive remains dirty when the live proxy says it is dirty.
    """

    session_uuid = self.identity_service.registered_session_uuid(document)
    with self._lock:
        foreign = self._foreign_records.get(session_uuid)
        if foreign is None:
            raise LeaseConflictError(
                "the registered document has no foreign recovery record"
            )
        previous = foreign.persisted
        if not self._is_missing_sidecar_foreign_recovery_candidate(previous):
            raise ForeignRecoveryError(
                "foreign authority lacks a verified recoverable saved baseline"
            )
        canonical_path = foreign.local_document.canonical_path
        if not canonical_path:
            raise ForeignRecoveryError(
                "orphan identity repair requires a saved document"
            )
        path = sidecar_path_for(canonical_path)
        if os.path.lexists(path):
            raise CoordinationError(
                "foreign sidecar still exists; identity repair is not automatic"
            )
        self._prove_orphaned_foreign_authority_inactive(foreign)
        observed = self.identity_service.inspect_registered_document(
            session_uuid, document
        )
        if (
            observed.name != foreign.local_document.name
            or observed.comparison_key != foreign.local_document.comparison_key
            or observed.comparison_key != previous.document.comparison_key
        ):
            raise ForeignRecoveryError(
                "live document name or path changed after foreign import"
            )
        baseline = previous.baseline
        if not isinstance(baseline, FileBaseline):
            raise ForeignRecoveryError(
                "foreign clean authority has no valid saved-file baseline"
            )
        self._assert_current_baseline(
            observed,
            baseline,
            error_type=ForeignRecoveryError,
        )
        refreshed = self.identity_service.refresh_saved_document(document)
        if (
            refreshed.session_uuid != session_uuid
            or refreshed.name != observed.name
            or refreshed.comparison_key != observed.comparison_key
            or refreshed.file_identity != observed.file_identity
        ):
            raise CoordinationError(
                "orphan identity refresh changed the live document binding"
            )
        self._foreign_records[session_uuid] = replace(foreign, local_document=refreshed)
        return refreshed


def list_foreign_recoveries(self) -> list[dict[str, Any]]:
    with self._lock:
        return [foreign.to_public_dict() for foreign in self._foreign_records.values()]
