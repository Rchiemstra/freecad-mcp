"""Document lease service operations — release clean."""

from __future__ import annotations

from typing import Any

from ..errors.clean_release_error import CleanReleaseError
from ..errors.coordination_error import CoordinationError
from ..errors.live_document_validation_error import LiveDocumentValidationError
from ..model import (
    LeaseCredential,
    LeaseErrorInfo,
    LeaseRecord,
    LeaseState,
    LiveDocumentValidation,
)
from ..sidecar import (
    SidecarError,
)
from .constants import (
    bounded_text,
)


def _clean_release_precondition_failures(record: LeaseRecord) -> list[str]:
    failures: list[str] = []
    if record.dirty:
        failures.append("document is dirty")
    if not record.validation_complete:
        failures.append("validation is incomplete")
    if record.error is not None:
        failures.append("an unresolved lease error exists")
    if record.baseline is None:
        failures.append("no verified file baseline exists")
    if record.document.canonical_path is None:
        failures.append("document has no saved path")
    if record.last_verified_save_revision < record.last_mutation_revision:
        failures.append("verified save predates the last mutation")
    return failures


def _remove_release_sidecar(
    self,
    credential: LeaseCredential,
    releasing: LeaseRecord,
) -> None:
    path = self._sidecar_path(releasing)
    try:
        if path is not None:
            self.sidecar_store.delete(path, expected=releasing)
    except SidecarError as exc:
        error_record = releasing.transitioned(
            LeaseState.LOCKED_ERROR,
            error=LeaseErrorInfo(
                code="SIDECAR_RELEASE_FAILED",
                message=bounded_text(str(exc), 2048),
                at=self._utc_clock(),
            ),
        )
        try:
            self._commit(releasing, error_record)
        except CoordinationError:
            self._records[credential.document_session_uuid] = error_record
        raise CoordinationError(
            f"clean release could not remove sidecar: {exc}"
        ) from exc


def release_clean(
    self,
    credential: LeaseCredential,
    *,
    validation: LiveDocumentValidation,
) -> dict[str, Any]:
    """CAS-remove a lease only after a clean, current, validated save."""

    with self._lock:
        record = self._record_for_credential(
            credential, allowed_states={LeaseState.LOCKED_IDLE}
        )
        try:
            self._validate_live_evidence(record, validation)
            if validation.document_modified:
                raise LiveDocumentValidationError(
                    "FreeCAD reports that the live document is dirty"
                )
        except LiveDocumentValidationError as exc:
            failed = record.transitioned(
                LeaseState.LOCKED_ERROR,
                error=LeaseErrorInfo(
                    code=exc.code,
                    message=bounded_text(str(exc), 2048),
                    at=self._utc_clock(),
                ),
                dirty=bool(
                    record.dirty or getattr(validation, "document_modified", False)
                ),
            )
            self._commit(record, failed)
            raise
        failures = _clean_release_precondition_failures(record)
        if failures:
            raise CleanReleaseError("; ".join(failures), details={"failures": failures})
        releasing = record.transitioned(
            LeaseState.RELEASING, current_operation="Finalizing lease"
        )
        self._commit(record, releasing)
        _remove_release_sidecar(self, credential, releasing)
        terminal = releasing.transitioned(
            LeaseState.UNLOCKED_SAVED, current_operation=""
        )
        result = terminal.to_public_dict()
        self._records.pop(credential.document_session_uuid, None)
        self._last_sidecar_heartbeat_ns.pop(credential.document_session_uuid, None)
        self._closed_documents.pop(
            credential.document_session_uuid,
            None,
        )
        return result
