"""Snapshot capture helpers for orphan recovery."""

from ._common import _rpc_mod, require_document_modified


def begin_saved_foreign_recovery(
    self,
    *,
    phase,
    adopt_dirty,
    task_description,
    observed,
    document_dirty,
    original_identity,
    lease,
):
    reservation = (
        _rpc_mod().document_lease_service.begin_saved_foreign_recovery_acquisition(
            phase["exact_selector"],
            phase["owner"],
            validation=lease.LiveDocumentValidation(
                document=observed,
                document_modified=document_dirty,
                baseline=phase["baseline"],
                baseline_validated=bool(original_identity.canonical_path),
            ),
            task_summary=task_description,
            adopt_dirty=adopt_dirty,
            local_confirmation=bool(
                phase.get("initial_dirty_adoption_authorized")
            ),
        )
    )
    credential = reservation.credential
    phase["credential"] = credential
    self._retain_inflight_credential(credential)
    return credential


def authorize_standard_snapshot(credential, original_identity, phase, lease):
    if phase.get("orphaned_local_mcp_recovery") or phase.get("orphaned_foreign_recovery"):
        return
    _rpc_mod().document_lease_service.authorize(
        credential,
        selector={"document_session_uuid": original_identity.session_uuid},
        allowed_states={lease.LeaseState.ACQUIRING},
    )


def capture_orphan_snapshot_gui(document, request_id, lease):
    if (
        lease.core_authority.core_owner_api_available(document)
        and lease.core_authority.authority_status(document) is None
    ):
        raise lease.CoordinationError(
            "core mutation authority status is unavailable "
            "for verified orphan recovery"
        )
    with lease.core_authority.open_mutation_capability(
        document,
        generation=0,
        kinds=("SaveAs",),
    ):
        return _rpc_mod().create_lease_baseline_snapshot_gui(
            document,
            observer_request_id=request_id,
        )


def validate_snapshot_dirty_state(adopt_dirty, document, lease):
    document_dirty = require_document_modified(document)
    if adopt_dirty and not document_dirty:
        raise lease.DirtyAdoptionError(
            "the document became clean while its recovery snapshot was captured"
        )
    if not adopt_dirty and document_dirty:
        raise lease.DirtyAcquisitionError(
            "document became dirty while its baseline snapshot was captured"
        )
    return document_dirty


def capture_prior_core_authority(document, phase, inflight, lease):
    prior_core_authority_status = None
    if not lease.core_authority.core_owner_api_available(document):
        return prior_core_authority_status
    prior_core_authority_status = lease.core_authority.authority_status(document)
    if prior_core_authority_status is None:
        raise lease.CoordinationError(
            "core mutation authority status changed or "
            "became unreadable during orphan recovery"
        )
    if inflight is not None:
        inflight.token.begin_irreversible(
            "local_orphan_authority_handoff"
            if phase.get("orphaned_local_mcp_recovery")
            else "foreign_orphan_authority_handoff"
        )
    return prior_core_authority_status
