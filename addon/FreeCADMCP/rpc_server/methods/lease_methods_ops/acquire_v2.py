"""Lease RPC methods extracted from ``FreeCADRPC`` (Phase 4 slice 4E)."""

from typing import Any

from ._common import _rpc_mod
from .acquire_v2_abort import abort_phase_reservation
from .acquire_v2_helpers import (
    handle_reserve_failure,
    handle_snapshot_timeout,
    locked_error_handoff_pending_response,
    run_hash_phase,
    validate_acquire_inputs,
)
from .acquire_v2_reserve_gui import reserve_gui as reserve_gui_phase
from .acquire_v2_snapshot import snapshot_and_promote_gui as snapshot_and_promote_gui_phase


def acquire_document_lock_v2(
    self,
    requested_selector,
    *,
    request_identity,
    task_description,
    client,
    agent_id,
    hash_policy,
    adopt_dirty=False,
):
    """Reserve first, hash off Qt, then snapshot/promote on Qt."""

    request_id = request_identity.get("request_id")
    task_description = _rpc_mod()._redact_rpc_diagnostic(
        task_description, identity=request_identity
    )[:1024]
    client = _rpc_mod()._redact_rpc_diagnostic(client, identity=request_identity)[:256]
    agent_id = _rpc_mod()._redact_rpc_diagnostic(agent_id, identity=request_identity)[
        :256
    ]
    invalid = validate_acquire_inputs(hash_policy)
    if invalid is not None:
        return invalid
    phase: dict[str, Any] = {}
    inflight = self._current_inflight()
    self._request_checkpoint("acquisition_start")
    acquire_timeout = self.ACQUIRE_GUI_PHASE_TIMEOUT_S

    self._request_checkpoint("acquisition_reserve_queue")

    def reserve_gui():
        return reserve_gui_phase(
            self,
            requested_selector=requested_selector,
            request_identity=request_identity,
            task_description=task_description,
            client=client,
            agent_id=agent_id,
            adopt_dirty=adopt_dirty,
            request_id=request_id,
            phase=phase,
            inflight=inflight,
        )

    try:
        reserved = self._dispatch_gui(reserve_gui, timeout=acquire_timeout)
    except Exception:
        abort_phase_reservation(phase)
        raise
    if not isinstance(reserved, dict) or not reserved.get("success"):
        return handle_reserve_failure(self, reserved, phase, inflight)

    if phase.get("locked_error_handoff_pending"):
        self._start_locked_error_handoff_continuation(
            request_id=request_id,
            mcp_runtime_id=str(request_identity.get("instance_id") or ""),
            requested_selector=requested_selector,
            task_description=task_description,
            phase=dict(phase),
        )
        return locked_error_handoff_pending_response(request_id)

    hash_result = run_hash_phase(
        self, phase, inflight, request_id, acquire_timeout
    )
    if hash_result is not None:
        return hash_result

    self._request_checkpoint("acquisition_snapshot_queue")

    def snapshot_and_promote_gui():
        return snapshot_and_promote_gui_phase(
            self,
            phase=phase,
            inflight=inflight,
            adopt_dirty=adopt_dirty,
            task_description=task_description,
            request_id=request_id,
        )

    promoted = self._dispatch_gui(snapshot_and_promote_gui, timeout=acquire_timeout)
    return handle_snapshot_timeout(self, promoted, phase, inflight)
