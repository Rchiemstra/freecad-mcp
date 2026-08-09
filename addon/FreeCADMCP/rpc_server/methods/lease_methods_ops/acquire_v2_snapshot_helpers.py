"""Snapshot-phase helpers for ``acquire_document_lock_v2``."""

from ._common import require_document_modified


def validate_snapshot_document_state(
    phase, adopt_dirty, document, original_identity, lease, collaborators
):
    observed = collaborators.document_identity_service.inspect_registered_document(
        original_identity.session_uuid, document
    )
    if (
        observed.comparison_key != original_identity.comparison_key
        or observed.file_identity != original_identity.file_identity
    ):
        raise lease.CoordinationError(
            "live document identity changed during acquisition"
        )
    document_dirty = require_document_modified(document)
    if adopt_dirty and not document_dirty:
        raise lease.DirtyAdoptionError(
            "the document became clean during dirty adoption"
        )
    if not adopt_dirty and document_dirty:
        raise lease.DirtyAcquisitionError(
            "document became dirty during acquisition"
        )
    return observed, document_dirty


def handle_snapshot_cancellation(self, inflight, snapshot_id, phase):
    collaborators = self._collaboration_collaborators
    effective_snapshot_id = snapshot_id or phase.get("snapshot_id")
    cancellation_events = self._complete_request_cancellation(
        inflight, dirty=True, snapshot_id=effective_snapshot_id
    )
    rolled_back = any(
        isinstance(event, dict) and event.get("rolled_back") is True
        for event in cancellation_events
    )
    if effective_snapshot_id and (
        rolled_back
        or (
            (
                phase.get("orphaned_local_mcp_recovery")
                or phase.get("orphaned_foreign_recovery")
            )
            and not phase.get("orphaned_authority_promoted")
        )
    ):
        collaborators.discard_lease_baseline_snapshot(effective_snapshot_id)


def abort_snapshot_on_failure(self, phase, snapshot_id, exc, request_id):
    collaborators = self._collaboration_collaborators
    promoted_orphan = bool(phase.get("orphaned_authority_promoted"))
    retain_recovery_snapshot = bool(getattr(exc, "details", {}).get("retain_snapshot"))
    effective_snapshot_id = snapshot_id or phase.get("snapshot_id")
    credential = phase.get("credential")
    if credential is not None and not promoted_orphan:
        try:
            collaborators.document_lease_service.abort_acquisition(credential)
        except Exception as rollback_exc:
            return collaborators.lease_service_error(
                rollback_exc, request_id=request_id
            )
    if effective_snapshot_id and not promoted_orphan and not retain_recovery_snapshot:
        collaborators.discard_lease_baseline_snapshot(effective_snapshot_id)
    return collaborators.lease_service_error(exc, request_id=request_id)
