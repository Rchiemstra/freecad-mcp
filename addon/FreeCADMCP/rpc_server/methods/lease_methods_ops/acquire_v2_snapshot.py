"""GUI snapshot and promote phase for ``acquire_document_lock_v2``."""

from ...inflight_requests import RequestCancellationError
from ._common import _rpc_mod
from .acquire_v2_snapshot_complete import complete_normal_acquisition
from .acquire_v2_snapshot_helpers import (
    abort_snapshot_on_failure,
    handle_snapshot_cancellation,
    validate_snapshot_document_state,
)
from .acquire_v2_snapshot_locked_handoff import grant_locked_error_handoff
from .acquire_v2_snapshot_orphan import (
    capture_acquisition_snapshot,
    complete_orphan_recovery,
)


def snapshot_and_promote_gui(
    self,
    *,
    phase,
    inflight,
    adopt_dirty,
    task_description,
    request_id,
):
    snapshot_id = None
    prior_core_authority_status = None
    marker_keys = []
    attribution_started = False
    try:
        if inflight is not None:
            inflight.token.checkpoint("acquisition_snapshot_gui")
        document = _rpc_mod().FreeCAD.getDocument(phase["document_name"])
        if document is None:
            raise RuntimeError("document closed while acquisition was preparing")
        original_identity = phase["document_identity"]
        marker_keys = {
            original_identity.name,
            original_identity.session_uuid,
            str(original_identity.canonical_path or ""),
        } - {""}
        dl = _rpc_mod()._import_document_lock()
        if not (
            phase.get("orphaned_local_mcp_recovery")
            or phase.get("orphaned_foreign_recovery")
        ):
            dl.begin_agent_mutation_scope(request_id, marker_keys)
            attribution_started = True
        observed, document_dirty = validate_snapshot_document_state(
            phase, adopt_dirty, document, original_identity, _rpc_mod()._import_document_lease()
        )
        if phase.get("locked_error_handoff"):
            return grant_locked_error_handoff(
                self,
                phase=phase,
                task_description=task_description,
                observed=observed,
                document=document,
                document_dirty=document_dirty,
                original_identity=original_identity,
            )
        snapshot_id, prior_core_authority_status, direct_orphan_recovery = (
            capture_acquisition_snapshot(
                self,
                phase=phase,
                adopt_dirty=adopt_dirty,
                task_description=task_description,
                request_id=request_id,
                inflight=inflight,
                observed=observed,
                document=document,
                document_dirty=document_dirty,
                original_identity=original_identity,
                credential=phase.get("credential"),
            )
        )
        credential = phase.get("credential")
        if direct_orphan_recovery:
            return complete_orphan_recovery(
                self,
                phase=phase,
                adopt_dirty=adopt_dirty,
                task_description=task_description,
                request_id=request_id,
                inflight=inflight,
                observed=observed,
                document=document,
                document_dirty=document_dirty,
                original_identity=original_identity,
                snapshot_id=snapshot_id,
                prior_core_authority_status=prior_core_authority_status,
            )
        return complete_normal_acquisition(
            self,
            phase=phase,
            adopt_dirty=adopt_dirty,
            credential=credential,
            snapshot_id=snapshot_id,
            document=document,
            original_identity=original_identity,
        )
    except RequestCancellationError:
        handle_snapshot_cancellation(self, inflight, snapshot_id, phase)
        raise
    except Exception as exc:
        return abort_snapshot_on_failure(self, phase, snapshot_id, exc, request_id)
    finally:
        dl = _rpc_mod()._import_document_lock()
        if attribution_started:
            dl.end_agent_mutation_scope(request_id, marker_keys)
