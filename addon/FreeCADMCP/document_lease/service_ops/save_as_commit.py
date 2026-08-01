"""Save As commit helpers for document lease service operations."""

from __future__ import annotations

import os
from dataclasses import replace

from ..errors.coordination_error import CoordinationError
from ..errors.lease_service_error import LeaseServiceError
from ..identity import canonicalize_path
from ..model import (
    FileBaseline,
    LeaseCredential,
    LeaseErrorInfo,
    LeaseRecord,
    LeaseState,
    SaveAsMigrationRole,
)
from ..sidecar import SidecarError
from .constants import bounded_text


def _assert_save_as_linkage(
    current: LeaseRecord,
    pending: LeaseRecord,
    comparison: str,
) -> None:
    if pending.document.comparison_key != comparison:
        raise CoordinationError("Save As destination reservation changed")
    source_migration = current.migration
    destination_migration = pending.migration
    if (
        source_migration is None
        or destination_migration is None
        or source_migration.role != SaveAsMigrationRole.SOURCE
        or destination_migration.role != SaveAsMigrationRole.DESTINATION
        or source_migration.migration_id != destination_migration.migration_id
        or replace(source_migration, role=SaveAsMigrationRole.DESTINATION)
        != destination_migration
    ):
        raise CoordinationError("Save As recovery linkage changed")


def _build_save_as_promoted_record(
    self,
    *,
    pending: LeaseRecord,
    current: LeaseRecord,
    session_uuid: str,
    canonical: str,
    baseline: FileBaseline,
    snapshot_id: str | None,
) -> LeaseRecord:
    updated_identity = self.identity_service.preview_path_update(
        session_uuid, canonical
    )
    return replace(
        pending,
        document=updated_identity,
        state=LeaseState.LOCKED_IDLE,
        record_revision=pending.record_revision + 1,
        state_revision=pending.state_revision + 1,
        current_operation="",
        dirty=False,
        error=None,
        baseline=baseline,
        last_successful_save_at=self._utc_clock(),
        last_verified_save_revision=current.last_mutation_revision,
        last_mutation_revision=current.last_mutation_revision,
        validation_complete=True,
        snapshot_id=bounded_text(snapshot_id, 512) or current.snapshot_id,
    )


def _publish_save_as_identity(
    self,
    *,
    session_uuid: str,
    canonical: str,
    updated_identity,
    promoted: LeaseRecord,
    destination_path: str,
) -> None:
    try:
        published_identity = self.identity_service.update_path(
            session_uuid, canonical
        )
        if published_identity != updated_identity:
            raise CoordinationError(
                "Save As destination identity changed during promotion"
            )
    except Exception as exc:
        error_record = promoted.transitioned(
            LeaseState.LOCKED_ERROR,
            error=LeaseErrorInfo(
                code="SAVE_AS_IDENTITY_REBIND_FAILED",
                message=bounded_text(str(exc), 2048),
                at=self._utc_clock(),
            ),
        )
        try:
            self.sidecar_store.replace(
                destination_path, error_record, expected=promoted
            )
        finally:
            self._records[session_uuid] = error_record
            self._pending_save_as.pop(session_uuid, None)
        if isinstance(exc, CoordinationError):
            raise
        raise CoordinationError(
            f"unable to publish Save As document identity: {exc}"
        ) from exc


def _release_save_as_source_sidecar(
    self,
    *,
    session_uuid: str,
    current: LeaseRecord,
    promoted: LeaseRecord,
    destination_path: str,
    source_path: str | None,
) -> None:
    try:
        if source_path is not None and source_path != destination_path:
            self.sidecar_store.delete(source_path, expected=current)
    except SidecarError as exc:
        error_record = promoted.transitioned(
            LeaseState.LOCKED_ERROR,
            error=LeaseErrorInfo(
                code="SAVE_AS_SOURCE_RELEASE_FAILED",
                message=bounded_text(str(exc), 2048),
                at=self._utc_clock(),
            ),
        )
        try:
            self.sidecar_store.replace(
                destination_path, error_record, expected=promoted
            )
        finally:
            self._records[session_uuid] = error_record
            self._pending_save_as.pop(session_uuid, None)
        raise CoordinationError(
            f"Save As retained its source recovery lock: {exc}"
        ) from exc


def _finalize_save_as_linkage(
    self,
    *,
    session_uuid: str,
    promoted: LeaseRecord,
    destination_path: str,
) -> LeaseRecord:
    finalized = promoted.revised(migration=None)
    try:
        self.sidecar_store.replace(
            destination_path,
            finalized,
            expected=promoted,
        )
    except SidecarError as exc:
        error_record = promoted.transitioned(
            LeaseState.LOCKED_ERROR,
            error=LeaseErrorInfo(
                code="SAVE_AS_LINKAGE_FINALIZE_FAILED",
                message=bounded_text(str(exc), 2048),
                at=self._utc_clock(),
            ),
        )
        try:
            self.sidecar_store.replace(
                destination_path, error_record, expected=promoted
            )
        except SidecarError:
            pass
        finally:
            self._records[session_uuid] = error_record
            self._pending_save_as.pop(session_uuid, None)
        raise CoordinationError(
            f"Save As recovery linkage could not be finalized: {exc}"
        ) from exc
    return finalized


def commit_save_as_record(
    self,
    credential: LeaseCredential,
    *,
    destination: str | os.PathLike[str],
    baseline: FileBaseline,
    snapshot_id: str | None = None,
) -> LeaseRecord:
    """Promote destination first, then CAS-remove the source sidecar last."""

    current = self._record_for_credential(
        credential, allowed_states={LeaseState.LOCKED_SAVING}
    )
    session_uuid = credential.document_session_uuid
    pending = self._pending_save_as.get(session_uuid)
    if pending is None:
        raise CoordinationError("Save As destination was not reserved")
    canonical, comparison = canonicalize_path(
        destination, platform=self.identity_service.platform
    )
    _assert_save_as_linkage(current, pending, comparison)
    promoted = _build_save_as_promoted_record(
        self,
        pending=pending,
        current=current,
        session_uuid=session_uuid,
        canonical=canonical,
        baseline=baseline,
        snapshot_id=snapshot_id,
    )
    destination_path = self._sidecar_path(pending)
    if destination_path is None:
        raise LeaseServiceError("Save As destination has no sidecar path")
    try:
        self.sidecar_store.replace(destination_path, promoted, expected=pending)
    except SidecarError as exc:
        raise CoordinationError(
            f"unable to promote Save As destination lease: {exc}"
        ) from exc

    _publish_save_as_identity(
        self,
        session_uuid=session_uuid,
        canonical=canonical,
        updated_identity=promoted.document,
        promoted=promoted,
        destination_path=destination_path,
    )
    source_path = self._sidecar_path(current)
    _release_save_as_source_sidecar(
        self,
        session_uuid=session_uuid,
        current=current,
        promoted=promoted,
        destination_path=destination_path,
        source_path=source_path,
    )
    finalized = _finalize_save_as_linkage(
        self,
        session_uuid=session_uuid,
        promoted=promoted,
        destination_path=destination_path,
    )
    self._records[session_uuid] = finalized
    self._pending_save_as.pop(session_uuid, None)
    self._last_sidecar_heartbeat_ns[session_uuid] = self._monotonic_ns()
    return finalized
