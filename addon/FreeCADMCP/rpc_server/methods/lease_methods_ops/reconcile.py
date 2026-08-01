"""Lease RPC methods extracted from ``FreeCADRPC`` (Phase 4 slice 4E)."""

from typing import Any

from ._common import _rpc_mod
from .reconcile_helpers import (
    capture_reconcile_baseline,
    commit_reconcile_gui,
    prepare_reconcile_gui,
)


def lease_reconcile(self, credential):
    if _rpc_mod().document_lease_service is None:
        return _rpc_mod()._lease_service_error(RuntimeError("lease service unavailable"))
    captured_identity = dict(_rpc_mod()._import_document_lock().get_request_identity())
    lease = _rpc_mod()._import_document_lease()
    phase: dict[str, Any] = {}
    inflight = self._current_inflight()
    self._request_checkpoint("lease_reconcile_start")

    def prepare_gui_phase():
        try:
            return prepare_reconcile_gui(
                self,
                credential=credential,
                inflight=inflight,
                captured_identity=captured_identity,
                phase=phase,
                lease=lease,
            )
        except Exception as exc:
            return _rpc_mod()._lease_service_error(
                exc, request_id=captured_identity.get("request_id")
            )

    self._request_checkpoint("lease_reconcile_prepare_queue")
    prepared = self._dispatch_gui(prepare_gui_phase)
    if not isinstance(prepared, dict) or not prepared.get("success"):
        return prepared
    if prepared.get("idempotent"):
        return {
            "success": True,
            "idempotent": True,
            "lease": prepared["lease"],
        }

    fresh_baseline = None
    if phase["reconcile_kind"] == "saved":
        baseline_result = capture_reconcile_baseline(
            self, phase, lease, captured_identity
        )
        if isinstance(baseline_result, dict) and not baseline_result.get("success", True):
            return baseline_result
        fresh_baseline = baseline_result

    def reconcile_gui_phase():
        try:
            return commit_reconcile_gui(
                self,
                inflight=inflight,
                captured_identity=captured_identity,
                phase=phase,
                lease=lease,
                fresh_baseline=fresh_baseline,
            )
        except Exception as exc:
            return _rpc_mod()._lease_service_error(
                exc, request_id=captured_identity.get("request_id")
            )

    self._request_checkpoint("lease_reconcile_commit_queue")
    return self._dispatch_gui(reconcile_gui_phase)
