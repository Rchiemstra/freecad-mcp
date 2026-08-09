"""Document lease service operations — stale ops."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from typing import Any

from ..errors.lease_conflict_error import LeaseConflictError
from ..errors.live_document_validation_error import LiveDocumentValidationError
from ..errors.local_recovery_error import LocalRecoveryError
from ..model import (
    DocumentSelector,
    LeaseCredential,
    LeaseErrorInfo,
    LeaseRecord,
    LeaseState,
    LiveDocumentValidation,
)
from .constants import (
    bounded_text,
)


def mark_stale(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    *,
    reason: str = "Lease heartbeat expired",
) -> LeaseRecord:
    identity = self.identity_service.resolve(selector)
    with self._lock:
        record = self._records.get(identity.session_uuid)
        if record is None:
            raise LeaseConflictError("the selected document has no active lease")
        self._assert_sidecar_matches(record)
        if record.state == LeaseState.STALE:
            return record
        updated = record.transitioned(
            LeaseState.STALE,
            error=LeaseErrorInfo(
                code="LEASE_STALE",
                message=bounded_text(reason, 2048),
                at=self._utc_clock(),
            ),
        )
        return self._commit(record, updated)


def mark_expired_stale(self, *, now_monotonic_ns: int | None = None) -> list[str]:
    """Persist stale state for expired leases without deleting anything."""

    now = self._monotonic_ns() if now_monotonic_ns is None else now_monotonic_ns
    changed: list[str] = []
    with self._lock:
        for session_uuid, record in list(self._records.items()):
            if record.state in {
                LeaseState.STALE,
                LeaseState.USER_INTERVENED,
                LeaseState.UNLOCKED_SAVED,
                LeaseState.UNLOCKED_DIRTY,
            }:
                continue
            owner_exit_proof = ""
            if (
                record.state == LeaseState.LOCKED_IDLE
                and self._is_recoverable_local_mcp_orphan_candidate(record)
            ):
                with contextlib.suppress(LocalRecoveryError):
                    owner_exit_proof = self._prove_local_mcp_owner_dead(record.owner)
            heartbeat_expired = (
                now - record.monotonic_heartbeat_ns > self._stale_after_ns
            )
            if not owner_exit_proof and not heartbeat_expired:
                continue
            error_code = "LEASE_OWNER_EXITED" if owner_exit_proof else "LEASE_STALE"
            error_message = (
                "Credential-owning MCP process exited: " + owner_exit_proof
                if owner_exit_proof
                else "Lease heartbeat expired"
            )
            updated = record.transitioned(
                LeaseState.STALE,
                error=LeaseErrorInfo(
                    code=error_code,
                    message=error_message,
                    at=self._utc_clock(),
                ),
            )
            self._commit(record, updated)
            changed.append(session_uuid)
    return changed


def reconcile_stale(
    self,
    credential: LeaseCredential,
    *,
    validation: LiveDocumentValidation,
) -> LeaseRecord:
    """Resume only when fresh live-document and baseline evidence is exact."""

    with self._lock:
        record = self._record_for_credential(
            credential, allowed_states={LeaseState.STALE}
        )
        try:
            self._validate_live_evidence(record, validation)
            if bool(validation.document_modified) != bool(record.dirty):
                raise LiveDocumentValidationError(
                    "live GUI document modified state no longer matches the stale record",
                    details={
                        "expected_modified": bool(record.dirty),
                        "actual_modified": bool(validation.document_modified),
                    },
                )
        except LiveDocumentValidationError as exc:
            failed = record.revised(
                error=LeaseErrorInfo(
                    code=exc.code,
                    message=bounded_text(str(exc), 2048),
                    at=self._utc_clock(),
                )
            )
            self._commit(record, failed)
            raise
        updated = record.transitioned(
            LeaseState.LOCKED_IDLE,
            error=None,
            last_heartbeat_at=self._utc_clock(),
            monotonic_heartbeat_ns=self._monotonic_ns(),
        )
        return self._commit(record, updated)
