"""Reservation-phase helpers for ``acquire_document_lock_v2``."""

from ._common import _rpc_mod, require_document_modified


def validate_dirty_adoption(document, document_identity, adopt_dirty, lease):
    if not adopt_dirty:
        document_dirty = require_document_modified(document)
        if document_dirty:
            raise lease.DirtyAcquisitionError(
                "a pre-existing dirty document requires local adoption"
            )
        return document_dirty
    if not _rpc_mod()._confirm_dirty_document_adoption_gui(
        document, document_identity
    ):
        raise lease.DirtyAdoptionError(
            "dirty-document adoption was not authorized"
        )
    document_dirty = require_document_modified(document)
    if not document_dirty:
        raise lease.DirtyAdoptionError(
            "the selected document has no unsaved changes to adopt"
        )
    if not document_identity.canonical_path:
        raise lease.DirtyAdoptionError(
            "initial dirty adoption currently requires an existing saved file"
        )
    return document_dirty


def build_lease_owner(request_identity, client, agent_id, lease):
    return lease.LeaseOwner(
        addon_profile_id=_rpc_mod().rpc_runtime_manifest.profile_id,
        addon_runtime_id=_rpc_mod().rpc_runtime_manifest.addon_runtime_id,
        freecad_pid=_rpc_mod().rpc_runtime_manifest.freecad_pid,
        freecad_process_started_at=(
            _rpc_mod().rpc_runtime_manifest.freecad_process_started_at
        ),
        boot_id=_rpc_mod().rpc_runtime_manifest.boot_id,
        mcp_instance_id=request_identity.get("instance_id") or "",
        mcp_pid=int(request_identity.get("pid") or 0),
        mcp_process_started_at=(
            request_identity.get("mcp_process_started_at")
            or _rpc_mod().addon_loaded_at
        ),
        hostname=_rpc_mod().document_lease_service.local_runtime_identity.hostname,
        mcp_hostname=request_identity.get("host") or "",
        client=client or request_identity.get("client") or "",
        agent_id=agent_id or request_identity.get("agent_id") or "",
    )


def begin_lease_reservation(
    self,
    *,
    adopt_dirty,
    exact_selector,
    owner,
    task_description,
    request_id,
    phase,
    lease,
):
    live_request_ids = (
        _rpc_mod().rpc_inflight_request_registry.active_lifecycle_request_ids()
        if _rpc_mod().rpc_inflight_request_registry is not None
        else frozenset()
    )
    try:
        if adopt_dirty:
            reservation = _rpc_mod().document_lease_service.begin_dirty_adoption(
                exact_selector,
                owner,
                task_summary=task_description,
                document_dirty=True,
                local_confirmation=True,
                acquisition_request_id=request_id,
                live_acquisition_request_ids=live_request_ids,
            )
        else:
            reservation = _rpc_mod().document_lease_service.begin_acquisition(
                exact_selector,
                owner,
                task_summary=task_description,
                document_dirty=False,
                acquisition_request_id=request_id,
                live_acquisition_request_ids=live_request_ids,
            )
    except lease.OrphanedForeignRecoveryRequired:
        phase["orphaned_foreign_recovery"] = True
        return None
    except lease.OrphanedLocalMcpRecoveryRequired:
        if adopt_dirty:
            raise
        phase["orphaned_local_mcp_recovery"] = True
        return None
    except lease.SavedForeignRecoveryRequired:
        phase["saved_foreign_recovery"] = True
        return None
    except lease.LockedErrorHandoffRequired:
        if not adopt_dirty:
            raise
        phase["locked_error_handoff_pending"] = True
        return None
    self._retain_inflight_credential(reservation.credential)
    phase["credential"] = reservation.credential
    return reservation
