"""Lease RPC methods extracted from ``FreeCADRPC`` (Phase 4 slice 4E)."""

import threading

from ._common import _rpc_mod
from .handoff_continuation import run_locked_error_handoff_continuation
from .handoff_escrow import escrow_locked_error_handoff_claim
from .handoff_journal import journal_handoff_terminal

__all__ = [
    "escrow_locked_error_handoff_claim",
    "journal_handoff_terminal",
    "run_locked_error_handoff_continuation",
    "start_locked_error_handoff_continuation",
]


def start_locked_error_handoff_continuation(
    self,
    *,
    request_id,
    mcp_runtime_id,
    requested_selector,
    task_description,
    phase,
):
    """Kick off automatic bounded handoff after a mutation-free detect."""

    if _rpc_mod().rpc_handoff_continuation_store is None or not mcp_runtime_id or not request_id:
        return
    _rpc_mod().rpc_handoff_continuation_store.begin(
        mcp_runtime_id=mcp_runtime_id, request_id=request_id
    )
    thread = threading.Thread(
        target=self._run_locked_error_handoff_continuation,
        kwargs={
            "request_id": request_id,
            "mcp_runtime_id": mcp_runtime_id,
            "requested_selector": dict(requested_selector or {}),
            "task_description": task_description,
            "phase": dict(phase),
        },
        name=f"FreeCADMCP-HandoffConfirm-{str(request_id)[:8]}",
        daemon=True,
    )
    thread.start()
