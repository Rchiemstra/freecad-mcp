"""Document lease service operations — begin acquisition."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Mapping
from typing import Any

from ..errors.lease_conflict_error import LeaseConflictError
from ..errors.lease_grant import LeaseGrant
from ..errors.lease_service_error import LeaseServiceError
from ..errors.local_recovery_error import LocalRecoveryError
from ..errors.locked_error_handoff_required import LockedErrorHandoffRequired
from ..errors.orphaned_foreign_recovery_required import OrphanedForeignRecoveryRequired
from ..errors.orphaned_local_mcp_recovery_required import (
    OrphanedLocalMcpRecoveryRequired,
)
from ..errors.saved_foreign_recovery_required import SavedForeignRecoveryRequired
from ..model import (
    DocumentSelector,
    LeaseCredential,
    LeaseOwner,
    LeaseRecord,
    LeaseState,
    token_fingerprint,
)
from ..sidecar import (
    SidecarError,
    sidecar_path_for,
)
from .constants import (
    bounded_text,
)


def _maybe_import_adjacent_foreign_recovery(self, identity) -> None:
    adjacent_path = (
        sidecar_path_for(identity.canonical_path) if identity.canonical_path else None
    )
    if adjacent_path is None or not os.path.lexists(adjacent_path):
        return
    with self._lock:
        known = bool(
            identity.session_uuid in self._records
            or identity.session_uuid in self._foreign_records
        )
    if known:
        return
    with contextlib.suppress(LeaseServiceError):
        self.import_adjacent_foreign_recovery(
            identity.session_uuid,
            live_document=identity,
        )


def _begin_acquisition_existing_conflict(
    self,
    existing: LeaseRecord,
    identity,
    owner: LeaseOwner,
    *,
    document_dirty: bool,
    replace_unreturned_reservation: bool,
    task_summary: str,
    acquisition_request_id: str | None,
    live_acquisition_request_ids: frozenset[str] | None,
) -> LeaseGrant | None:
    if (
        document_dirty
        and existing.state == LeaseState.LOCKED_ERROR
        and existing.dirty
        and not existing.user_intervened
    ):
        raise LockedErrorHandoffRequired(
            "a dirty local LOCKED_ERROR lease requires confirmed "
            "credential handoff",
            details=existing.to_public_dict(),
        )
    if (
        not document_dirty
        and existing.owner.mcp_instance_id != owner.mcp_instance_id
        and self._is_recoverable_local_mcp_orphan_candidate(existing)
    ):
        try:
            self._prove_local_mcp_recovery_authority_inactive(existing)
        except LocalRecoveryError:
            pass
        else:
            raise OrphanedLocalMcpRecoveryRequired(
                "a saved local lease has inactive credential "
                "authority and requires verified in-process fencing",
                details=existing.to_public_dict(),
            )
    if replace_unreturned_reservation and self._is_unreturned_reservation(
        existing,
        allow_active_acquiring=self._may_fence_local_active_acquiring(
            existing,
            owner,
            session_uuid=identity.session_uuid,
            live_acquisition_request_ids=live_acquisition_request_ids,
        ),
    ):
        return self._replace_unreturned_reservation(
            existing,
            identity,
            owner,
            task_summary=task_summary,
            document_dirty=document_dirty,
            acquisition_request_id=acquisition_request_id,
        )
    raise LeaseConflictError(
        "the live document already has a lease",
        details=existing.to_public_dict(),
    )


def _begin_acquisition_foreign_conflict(
    self,
    foreign,
    identity,
    owner: LeaseOwner,
    *,
    document_dirty: bool,
    replace_unreturned_reservation: bool,
    task_summary: str,
    acquisition_request_id: str | None,
) -> LeaseGrant | None:
    foreign_path = (
        sidecar_path_for(identity.canonical_path) if identity.canonical_path else None
    )
    if (
        replace_unreturned_reservation
        and foreign_path is not None
        and not os.path.lexists(foreign_path)
        and self._is_missing_sidecar_foreign_recovery_candidate(foreign.persisted)
    ):
        raise OrphanedForeignRecoveryRequired(
            "a recoverable foreign record lost its sidecar and "
            "requires verified in-process fencing",
            details=foreign.to_public_dict(),
        )
    if replace_unreturned_reservation and self._is_unreturned_reservation(
        foreign.persisted,
        allow_active_acquiring=True,
    ):
        return self._replace_unreturned_reservation(
            foreign.persisted,
            identity,
            owner,
            task_summary=task_summary,
            document_dirty=document_dirty,
            foreign=foreign,
            acquisition_request_id=acquisition_request_id,
        )
    if (
        foreign_path is not None
        and os.path.lexists(foreign_path)
        and (
            self._is_saved_dirty_foreign_candidate(foreign.persisted)
            or self._is_abandoned_locked_error_foreign_candidate(foreign.persisted)
        )
    ):
        raise SavedForeignRecoveryRequired(
            "a document is blocked by recoverable dirty authority from "
            "another runtime and requires verified in-process fencing",
            details=foreign.to_public_dict(),
        )
    raise LeaseConflictError(
        "a foreign recovery record owns the live document",
        details=foreign.to_public_dict(),
    )


def _publish_new_acquisition_record(
    self,
    identity,
    owner: LeaseOwner,
    *,
    task_summary: str,
    document_dirty: bool,
    acquisition_request_id: str | None,
) -> LeaseGrant:
    generation = self._generations.get(identity.session_uuid, 0) + 1
    raw_token = self._token_factory()
    if not raw_token:
        raise LeaseServiceError("token factory returned an empty token")
    now = self._utc_clock()
    now_mono = self._monotonic_ns()
    record = LeaseRecord(
        lease_id=str(self._uuid_factory()),
        generation=generation,
        token_fingerprint=token_fingerprint(raw_token),
        document=identity,
        owner=owner,
        state=LeaseState.ACQUIRING,
        record_revision=1,
        state_revision=1,
        acquired_at=now,
        last_heartbeat_at=now,
        monotonic_heartbeat_ns=now_mono,
        task_summary=bounded_text(task_summary, 1024),
        dirty=document_dirty,
        last_mutation_revision=1 if document_dirty else 0,
        baseline=None,
        validation_complete=False,
        snapshot_id=None,
    )
    path = self._sidecar_path(record)
    if path is not None:
        try:
            self.sidecar_store.create(path, record)
        except SidecarError as exc:
            raise LeaseConflictError(
                f"document sidecar prevents acquisition: {exc}"
            ) from exc
    self._records[identity.session_uuid] = record
    self._generations[identity.session_uuid] = generation
    self._last_sidecar_heartbeat_ns[identity.session_uuid] = now_mono
    self._remember_acquiring_request(identity.session_uuid, acquisition_request_id)
    credential = LeaseCredential(
        lease_id=record.lease_id,
        document_session_uuid=identity.session_uuid,
        generation=generation,
        token=raw_token,
        mcp_instance_id=owner.mcp_instance_id,
    )
    return LeaseGrant(credential=credential, record=record)


def _begin_acquisition_record(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    owner: LeaseOwner,
    *,
    task_summary: str,
    document_dirty: bool,
    replace_unreturned_reservation: bool = False,
    acquisition_request_id: str | None = None,
    live_acquisition_request_ids: frozenset[str] | None = None,
) -> LeaseGrant:
    """Publish one clean acquisition or confirmed dirty-adoption record."""

    identity = self.identity_service.resolve(selector)
    _maybe_import_adjacent_foreign_recovery(self, identity)
    with self._lock:
        existing = self._records.get(identity.session_uuid)
        if existing is not None:
            return _begin_acquisition_existing_conflict(
                self,
                existing,
                identity,
                owner,
                document_dirty=document_dirty,
                replace_unreturned_reservation=replace_unreturned_reservation,
                task_summary=task_summary,
                acquisition_request_id=acquisition_request_id,
                live_acquisition_request_ids=live_acquisition_request_ids,
            )
        foreign = self._foreign_records.get(identity.session_uuid)
        if foreign is not None:
            return _begin_acquisition_foreign_conflict(
                self,
                foreign,
                identity,
                owner,
                document_dirty=document_dirty,
                replace_unreturned_reservation=replace_unreturned_reservation,
                task_summary=task_summary,
                acquisition_request_id=acquisition_request_id,
            )
        return _publish_new_acquisition_record(
            self,
            identity,
            owner,
            task_summary=task_summary,
            document_dirty=document_dirty,
            acquisition_request_id=acquisition_request_id,
        )
