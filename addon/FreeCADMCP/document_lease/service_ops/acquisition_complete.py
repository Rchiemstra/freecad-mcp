"""Document lease service operations — acquisition complete."""

from __future__ import annotations

import uuid
from typing import Any

from ..errors.coordination_error import CoordinationError
from ..errors.lease_grant import LeaseGrant
from ..errors.lease_service_error import LeaseServiceError
from ..model import (
    FileBaseline,
    LeaseCredential,
    LeaseErrorInfo,
    LeaseRecord,
    LeaseState,
)
from ..sidecar import (
    SidecarError,
)
from .acquisition_validation import (
    assert_acquisition_snapshot_authority,
    normalize_acquisition_snapshot_id,
    validate_acquisition_reservation,
    validate_saved_document_acquisition,
    validate_unsaved_document_acquisition,
)
from .constants import (
    bounded_text,
)


def complete_dirty_adoption(
    self,
    credential: LeaseCredential,
    *,
    baseline: FileBaseline,
    baseline_validated: bool,
    snapshot_id: str,
) -> LeaseGrant:
    """Promote only an ACQUIRING record created for dirty adoption."""

    return self._complete_acquisition_record(
        credential,
        baseline=baseline,
        baseline_validated=baseline_validated,
        snapshot_id=snapshot_id,
        expected_dirty=True,
    )


def record_acquisition_snapshot(
    self,
    credential: LeaseCredential,
    *,
    snapshot_id: str,
) -> LeaseRecord:
    """Persist recovery-snapshot authority before acquisition promotion."""

    try:
        normalized_snapshot = str(uuid.UUID(str(snapshot_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise LeaseServiceError("acquisition snapshot ID must be a UUID") from exc
    with self._lock:
        record = self._record_for_credential(
            credential,
            allowed_states={LeaseState.ACQUIRING},
        )
        if record.snapshot_id is not None:
            if record.snapshot_id != normalized_snapshot:
                raise CoordinationError(
                    "acquisition snapshot authority already changed"
                )
            return record
        updated = record.revised(snapshot_id=normalized_snapshot)
        return self._commit(record, updated)


def complete_acquisition(
    self,
    credential: LeaseCredential,
    *,
    baseline: FileBaseline | None,
    baseline_validated: bool,
    snapshot_id: str | None,
) -> LeaseGrant:
    """Promote only an exact clean reservation with complete evidence."""

    return self._complete_acquisition_record(
        credential,
        baseline=baseline,
        baseline_validated=baseline_validated,
        snapshot_id=snapshot_id,
        expected_dirty=False,
    )


def _complete_acquisition_record(
    self,
    credential: LeaseCredential,
    *,
    baseline: FileBaseline | None,
    baseline_validated: bool,
    snapshot_id: str | None,
    expected_dirty: bool,
) -> LeaseGrant:
    """Promote one exact reservation with complete saved-file evidence."""

    with self._lock:
        record = self._record_for_credential(
            credential, allowed_states={LeaseState.ACQUIRING}
        )
        validate_acquisition_reservation(record, expected_dirty=expected_dirty)
        path = record.document.canonical_path
        normalized_snapshot = normalize_acquisition_snapshot_id(snapshot_id)
        assert_acquisition_snapshot_authority(record, normalized_snapshot)
        if path:
            validate_saved_document_acquisition(
                path=path,
                baseline=baseline,
                baseline_validated=baseline_validated,
                normalized_snapshot=normalized_snapshot,
                identity_platform=self.identity_service.platform,
                record=record,
            )
        else:
            validate_unsaved_document_acquisition(path, baseline, baseline_validated)
        idle = record.transitioned(
            LeaseState.LOCKED_IDLE,
            baseline=baseline,
            validation_complete=bool(path and baseline_validated),
            snapshot_id=normalized_snapshot,
        )
        try:
            idle = self._commit(record, idle)
        except CoordinationError:
            # Keep ACQUIRING in memory and on disk. The token is still
            # private, so only guarded recovery can resolve uncertainty.
            raise
        self._clear_acquiring_request(credential.document_session_uuid)
        return LeaseGrant(credential=credential, record=idle)


def abort_acquisition(self, credential: LeaseCredential) -> dict[str, Any]:
    """CAS-remove an unreturned, mutation-free ACQUIRING reservation."""

    with self._lock:
        record = self._record_for_credential(
            credential, allowed_states={LeaseState.ACQUIRING}
        )
        path = self._sidecar_path(record)
        try:
            if path is not None:
                self.sidecar_store.delete(path, expected=record)
        except SidecarError as exc:
            error_record = record.transitioned(
                LeaseState.LOCKED_ERROR,
                error=LeaseErrorInfo(
                    code="ACQUISITION_ROLLBACK_FAILED",
                    message=bounded_text(str(exc), 2048),
                    at=self._utc_clock(),
                ),
            )
            try:
                self._commit(record, error_record)
            except CoordinationError:
                self._records[credential.document_session_uuid] = error_record
            raise CoordinationError(
                f"acquisition reservation could not be rolled back: {exc}"
            ) from exc
        self._records.pop(credential.document_session_uuid, None)
        self._last_sidecar_heartbeat_ns.pop(credential.document_session_uuid, None)
        self._closed_documents.pop(
            credential.document_session_uuid,
            None,
        )
        self._clear_acquiring_request(credential.document_session_uuid)
        return {
            "rolled_back": True,
            "document_session_uuid": credential.document_session_uuid,
            "generation": credential.generation,
        }


def fail_acquisition_after_mutation(
    self,
    credential: LeaseCredential,
    *,
    request_id: str,
    message: str,
    dirty: bool = True,
    snapshot_id: str | None = None,
) -> LeaseRecord:
    """Retain acquisition authority after a live-state mutation.

    An acquisition credential has not yet been returned, so silently
    aborting after mutation would orphan changed state.  This exact typed
    event preserves the sidecar/registry fence for local recovery.
    """

    normalized_snapshot = None
    if snapshot_id:
        try:
            normalized_snapshot = str(uuid.UUID(str(snapshot_id)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise LeaseServiceError(
                "acquisition cancellation snapshot ID must be a UUID"
            ) from exc
    with self._lock:
        record = self._record_for_credential(
            credential,
            allowed_states={
                LeaseState.ACQUIRING,
                LeaseState.LOCKED_IDLE,
                LeaseState.LOCKED_ERROR,
            },
        )
        error = LeaseErrorInfo(
            code="REQUEST_CANCELLED_AFTER_MUTATION",
            message=bounded_text(message, 2048),
            at=self._utc_clock(),
            request_id=bounded_text(request_id, 64) or None,
        )
        changes: dict[str, Any] = {
            "current_operation": "",
            "dirty": bool(dirty),
            "validation_complete": False,
            "error": error,
        }
        if normalized_snapshot is not None:
            changes["snapshot_id"] = normalized_snapshot
        if record.state == LeaseState.LOCKED_ERROR:
            updated = record.revised(**changes)
        else:
            updated = record.transitioned(LeaseState.LOCKED_ERROR, **changes)
        return self._commit(record, updated)
