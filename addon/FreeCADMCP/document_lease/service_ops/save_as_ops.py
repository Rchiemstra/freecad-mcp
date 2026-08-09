"""Document lease service operations — save as ops."""

from __future__ import annotations

import os
import uuid
from dataclasses import replace

from ..errors.clean_release_error import CleanReleaseError
from ..errors.coordination_error import CoordinationError
from ..errors.lease_conflict_error import LeaseConflictError
from ..errors.lease_service_error import LeaseServiceError
from ..identity import (
    capture_file_baseline,
)
from ..model import (
    FileBaseline,
    LeaseCredential,
    LeaseRecord,
    LeaseState,
    SaveAsMigration,
    SaveAsMigrationRole,
)
from ..sidecar import (
    SidecarError,
)
from .constants import (
    bounded_text,
)
from .save_as_commit import commit_save_as_record


def reserve_save_as(
    self, credential: LeaseCredential, destination: str | os.PathLike[str]
) -> LeaseRecord:
    """Publish a destination recovery record before FreeCAD calls saveAs()."""

    with self._lock:
        record = self._record_for_credential(
            credential, allowed_states={LeaseState.LOCKED_SAVING}
        )
        session_uuid = credential.document_session_uuid
        if session_uuid in self._pending_save_as:
            raise LeaseConflictError("a Save As reservation already exists")
        destination_identity = self.identity_service.preview_path_update(
            session_uuid, destination
        )
        migration_id = str(uuid.uuid4())
        source_migration = SaveAsMigration(
            migration_id=migration_id,
            source_canonical_path=record.document.canonical_path,
            source_comparison_key=record.document.comparison_key,
            destination_canonical_path=destination_identity.canonical_path or "",
            destination_comparison_key=destination_identity.comparison_key or "",
            role=SaveAsMigrationRole.SOURCE,
        )
        destination_migration = replace(
            source_migration,
            role=SaveAsMigrationRole.DESTINATION,
        )
        pending = replace(
            record,
            document=destination_identity,
            state=LeaseState.ACQUIRING,
            record_revision=1,
            state_revision=1,
            current_operation="Save As destination reserved",
            baseline=None,
            validation_complete=False,
            migration=destination_migration,
        )
        path = self._sidecar_path(pending)
        if path is None:
            raise LeaseServiceError("Save As destination has no sidecar path")
        try:
            self.sidecar_store.create(path, pending)
        except SidecarError as exc:
            raise LeaseConflictError(
                f"Save As destination is locked or unavailable: {exc}"
            ) from exc
        self._pending_save_as[session_uuid] = pending
        source_linked = record.revised(migration=source_migration)
        try:
            self._commit(record, source_linked)
        except CoordinationError:
            # The destination reservation remains authoritative and
            # self-describes its source.  The caller may explicitly cancel
            # before saveAs; a crash leaves both paths safely fenced.
            raise
        return pending


def commit_save_as(
    self,
    credential: LeaseCredential,
    *,
    destination: str | os.PathLike[str],
    baseline: FileBaseline,
    snapshot_id: str | None = None,
) -> LeaseRecord:
    """Promote destination first, then CAS-remove the source sidecar last."""

    with self._lock:
        return commit_save_as_record(
            self,
            credential,
            destination=destination,
            baseline=baseline,
            snapshot_id=snapshot_id,
        )


def mark_save_verified(
    self,
    credential: LeaseCredential,
    *,
    baseline: FileBaseline | None = None,
    snapshot_id: str | None = None,
) -> LeaseRecord:
    with self._lock:
        record = self._record_for_credential(
            credential, allowed_states={LeaseState.LOCKED_SAVING}
        )
        if baseline is None:
            path = record.document.canonical_path
            if not path:
                raise CleanReleaseError(
                    "an unsaved document cannot be verified without a saved path"
                )
            baseline = capture_file_baseline(
                path, platform=self.identity_service.platform
            )
        refreshed_document = record.document
        if record.document.canonical_path:
            # FreeCAD may implement save via temporary-file replacement,
            # changing the filesystem identity while preserving the path.
            refreshed_document = self.identity_service.update_path(
                record.document.session_uuid, record.document.canonical_path
            )
        updated = record.transitioned(
            LeaseState.LOCKED_IDLE,
            document=refreshed_document,
            current_operation="",
            dirty=False,
            error=None,
            baseline=baseline,
            last_successful_save_at=self._utc_clock(),
            last_verified_save_revision=record.last_mutation_revision,
            validation_complete=True,
            snapshot_id=bounded_text(snapshot_id, 512) or record.snapshot_id,
        )
        return self._commit(record, updated)
