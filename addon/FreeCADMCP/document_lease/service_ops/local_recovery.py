"""Document lease service operations — local recovery."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from ..errors.coordination_error import CoordinationError
from ..errors.lease_conflict_error import LeaseConflictError
from ..errors.lease_state_error import LeaseStateError
from ..errors.local_recovery_error import LocalRecoveryError
from ..identity import (
    DocumentIdentityError,
    file_identity_for_path,
)
from ..model import (
    DocumentSelector,
    FileBaseline,
    LeaseErrorInfo,
    LeaseRecord,
    LeaseState,
)
from ..sidecar import (
    SidecarError,
)
from .constants import (
    bounded_text,
)


def _validate_local_save_inputs(
    *,
    verified_baseline: FileBaseline,
    baseline_validated: bool,
    document_modified: bool,
) -> None:
    if not isinstance(verified_baseline, FileBaseline):
        raise LocalRecoveryError("a verified file baseline is required")
    if baseline_validated is not True:
        raise LocalRecoveryError(
            "independent archive/domain baseline validation is required"
        )
    if document_modified:
        raise LocalRecoveryError("FreeCAD still reports the document as dirty")


def _assert_local_save_record_state(self, identity, record: LeaseRecord) -> None:
    if record is None:
        raise LeaseConflictError("the selected document has no recovery record")
    if record.state not in {
        LeaseState.USER_INTERVENED,
        LeaseState.UNLOCKED_DIRTY,
    }:
        raise LeaseStateError(
            "local save-and-clear requires takeover or dirty acknowledgement",
            details={"state": record.state.value},
        )
    if identity.session_uuid in self._pending_save_as:
        raise LocalRecoveryError(
            "a pending Save As destination requires guarded recovery"
        )
    self._assert_sidecar_matches(record)


def _revalidate_verified_baseline(
    self,
    path: str,
    verified_baseline: FileBaseline,
) -> None:
    try:
        info = os.stat(path)
        current_identity = file_identity_for_path(
            path, platform=self.identity_service.platform
        )
    except (DocumentIdentityError, OSError) as exc:
        raise LocalRecoveryError(
            f"unable to revalidate the saved document: {exc}"
        ) from exc
    if (
        int(info.st_size) != verified_baseline.size
        or int(info.st_mtime_ns) != verified_baseline.mtime_ns
        or current_identity != verified_baseline.file_identity
    ):
        raise LocalRecoveryError("the saved file changed after verification")


def _refresh_saved_document_identity(
    self,
    identity,
    path: str,
    verified_baseline: FileBaseline,
):
    try:
        refreshed_document = self.identity_service.update_path(
            identity.session_uuid, path
        )
    except Exception as exc:
        raise LocalRecoveryError(
            f"unable to refresh saved document identity: {exc}"
        ) from exc
    if (
        verified_baseline.file_identity is not None
        and refreshed_document.file_identity != verified_baseline.file_identity
    ):
        raise LocalRecoveryError(
            "saved document identity does not match its verified baseline"
        )
    return refreshed_document


def _remove_local_recovery_sidecar(
    self,
    identity,
    record: LeaseRecord,
    releasing: LeaseRecord,
) -> None:
    sidecar_path = self._sidecar_path(releasing)
    try:
        if sidecar_path is not None:
            self.sidecar_store.delete(sidecar_path, expected=releasing)
    except SidecarError as exc:
        failed = releasing.transitioned(
            LeaseState.LOCKED_ERROR,
            error=LeaseErrorInfo(
                code="LOCAL_SIDECAR_RELEASE_FAILED",
                message=bounded_text(str(exc), 2048),
                at=self._utc_clock(),
            ),
        )
        try:
            self._commit(releasing, failed)
        except CoordinationError:
            self._records[identity.session_uuid] = failed
        raise CoordinationError(
            f"local save succeeded but sidecar removal failed: {exc}"
        ) from exc


def acknowledge_local_dirty(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    *,
    document_dirty: bool,
    reason: str = "Local user chose to keep the document dirty",
) -> LeaseRecord:
    """Persist ``UNLOCKED_DIRTY`` after an explicit local confirmation."""

    if document_dirty is not True:
        raise LocalRecoveryError(
            "keep-dirty acknowledgement requires a currently dirty document"
        )
    identity = self.identity_service.resolve(selector)
    with self._lock:
        record = self._records.get(identity.session_uuid)
        if record is None:
            raise LeaseConflictError("the selected document has no recovery record")
        if record.state == LeaseState.UNLOCKED_DIRTY:
            return record
        if record.state != LeaseState.USER_INTERVENED:
            raise LeaseStateError(
                "keep-dirty acknowledgement requires a prior local takeover",
                details={"state": record.state.value},
            )
        if identity.session_uuid in self._pending_save_as:
            raise LocalRecoveryError(
                "a pending Save As destination requires guarded recovery"
            )
        self._assert_sidecar_matches(record)
        updated = record.transitioned(
            LeaseState.UNLOCKED_DIRTY,
            current_operation="",
            dirty=True,
            user_intervened=True,
            validation_complete=False,
            error=LeaseErrorInfo(
                code="DIRTY_ACKNOWLEDGED",
                message=bounded_text(reason, 2048),
                at=self._utc_clock(),
            ),
        )
        return self._commit(record, updated)


def complete_local_save_and_clear(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    *,
    verified_baseline: FileBaseline,
    baseline_validated: bool,
    document_modified: bool,
) -> dict[str, Any]:
    """CAS-clear a locally recovered lease after an independently verified save.

    The GUI must first use ``SaveService`` with archive, matching-worker,
    and domain validation. This method performs only the final lightweight
    stat/file-identity and GUI-document modified-state checks before publishing
    ``RELEASING`` and compare-and-removing the sidecar. No full hash runs
    under the service lock or on Qt, and no lease token is accepted.
    """

    _validate_local_save_inputs(
        verified_baseline=verified_baseline,
        baseline_validated=baseline_validated,
        document_modified=document_modified,
    )
    identity = self.identity_service.resolve(selector)
    with self._lock:
        record = self._records.get(identity.session_uuid)
        _assert_local_save_record_state(self, identity, record)
        path = record.document.canonical_path
        if not path:
            raise LocalRecoveryError(
                "an unsaved document requires guarded Save As recovery"
            )
        _revalidate_verified_baseline(self, path, verified_baseline)
        refreshed_document = _refresh_saved_document_identity(
            self,
            identity,
            path,
            verified_baseline,
        )

        releasing = record.transitioned(
            LeaseState.RELEASING,
            document=refreshed_document,
            current_operation="Local save verified; clearing lease",
            dirty=False,
            error=None,
            baseline=verified_baseline,
            last_successful_save_at=self._utc_clock(),
            last_verified_save_revision=record.last_mutation_revision,
            validation_complete=True,
        )
        self._commit(record, releasing)
        _remove_local_recovery_sidecar(self, identity, record, releasing)

        terminal = releasing.transitioned(
            LeaseState.UNLOCKED_SAVED, current_operation=""
        )
        result = terminal.to_public_dict()
        self._records.pop(identity.session_uuid, None)
        self._last_sidecar_heartbeat_ns.pop(identity.session_uuid, None)
        self._closed_documents.pop(identity.session_uuid, None)
        return result
