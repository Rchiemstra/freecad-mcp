"""Orphan-recovery promotion during acquisition snapshot."""

from .acquire_v2_snapshot_capture_helpers import (
    authorize_standard_snapshot,
    begin_saved_foreign_recovery,
    capture_orphan_snapshot_gui,
    capture_prior_core_authority,
    validate_snapshot_dirty_state,
)


def complete_orphan_recovery(
    self,
    *,
    phase,
    adopt_dirty,
    task_description,
    request_id,
    inflight,
    observed,
    document,
    document_dirty,
    original_identity,
    snapshot_id,
    prior_core_authority_status,
):
    collaborators = self._collaboration_collaborators
    lease = collaborators.import_document_lease()

    def escrow_recovery_grant(recovery_grant):
        if collaborators.acquisition_claim_store is None:
            return False
        escrow_result = {
            "success": True,
            **recovery_grant.to_dict(),
            "expiry_policy": {
                "heartbeat_interval_seconds": 10,
                "sidecar_flush_interval_seconds": 30,
                "stale_after_seconds": 90,
            },
        }
        collaborators.acquisition_claim_store.store(
            mcp_runtime_id=phase["owner"].mcp_instance_id,
            request_id=request_id,
            method=(
                "adopt_dirty_document" if adopt_dirty else "acquire_document_lock"
            ),
            credential=escrow_result["credential"],
            result=escrow_result,
        )
        return True

    if phase.get("orphaned_local_mcp_recovery"):
        grant = collaborators.document_lease_service.recover_orphaned_local_mcp_acquisition(
            phase["exact_selector"],
            phase["owner"],
            validation=lease.LiveDocumentValidation(
                document=observed,
                document_modified=document_dirty,
                baseline=phase["baseline"],
                baseline_validated=bool(original_identity.canonical_path),
            ),
            snapshot_id=snapshot_id,
            task_summary=task_description,
            authority_handoff=lambda replacement: (
                lease.core_authority.sync_mcp_owner_verified(document, replacement)
            ),
            authority_rollback=lambda: (
                lease.core_authority.restore_authority_status(
                    document, prior_core_authority_status
                )
            ),
            credential_escrow=escrow_recovery_grant,
        )
    else:
        grant = collaborators.document_lease_service.recover_orphaned_foreign_acquisition(
            phase["exact_selector"],
            phase["owner"],
            validation=lease.LiveDocumentValidation(
                document=observed,
                document_modified=document_dirty,
                baseline=phase["baseline"],
                baseline_validated=bool(original_identity.canonical_path),
            ),
            snapshot_id=snapshot_id,
            task_summary=task_description,
            adopt_dirty=adopt_dirty,
            local_confirmation=bool(phase.get("initial_dirty_adoption_authorized")),
            authority_handoff=lambda replacement: (
                lease.core_authority.sync_mcp_owner_verified(document, replacement)
            ),
            authority_rollback=lambda: (
                lease.core_authority.restore_authority_status(
                    document, prior_core_authority_status
                )
            ),
            credential_escrow=escrow_recovery_grant,
        )
    credential = grant.credential
    phase["credential"] = credential
    phase["orphaned_authority_promoted"] = True
    self._retain_inflight_credential(credential)
    return {
        "success": True,
        **grant.to_dict(),
        "expiry_policy": {
            "heartbeat_interval_seconds": 10,
            "sidecar_flush_interval_seconds": 30,
            "stale_after_seconds": 90,
        },
    }


def capture_acquisition_snapshot(
    self,
    *,
    phase,
    adopt_dirty,
    task_description,
    request_id,
    inflight,
    observed,
    document,
    document_dirty,
    original_identity,
    credential,
):
    collaborators = self._collaboration_collaborators
    lease = collaborators.import_document_lease()
    if phase.get("saved_foreign_recovery"):
        credential = begin_saved_foreign_recovery(
            self,
            phase=phase,
            adopt_dirty=adopt_dirty,
            task_description=task_description,
            observed=observed,
            document_dirty=document_dirty,
            original_identity=original_identity,
            lease=lease,
        )
    else:
        authorize_standard_snapshot(
            credential, original_identity, phase, lease, collaborators
        )
    direct_orphan_recovery = bool(
        phase.get("orphaned_local_mcp_recovery")
        or phase.get("orphaned_foreign_recovery")
    )
    if direct_orphan_recovery:
        snapshot_id = capture_orphan_snapshot_gui(
            document, request_id, lease, collaborators
        )
    else:
        snapshot_id = collaborators.create_lease_baseline_snapshot_gui(document)
    phase["snapshot_id"] = snapshot_id
    if inflight is not None:
        inflight.token.checkpoint("acquisition_snapshot_complete")
    document_dirty = validate_snapshot_dirty_state(adopt_dirty, document, lease)
    prior_core_authority_status = None
    if direct_orphan_recovery:
        prior_core_authority_status = capture_prior_core_authority(
            document, phase, inflight, lease
        )
    return snapshot_id, prior_core_authority_status, direct_orphan_recovery
