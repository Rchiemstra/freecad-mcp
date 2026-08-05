"""MCP tool registration — runtime control (Phase 7 / 7D)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    claim_acquisition_result_operation,
)
from .outcomes import OutcomeStatus
from .responses import json_response, tool_fail

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_check_rpc_sync(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def check_rpc_sync(ctx: Context) -> CallToolResult:
        """Verify that the next FreeCAD GUI response belongs to this exact call.

        A unique nonce is round-tripped through FreeCAD's GUI task queue. Use this
        after an execute timeout or before relying on model inspection results. A
        timeout or nonce mismatch means the queue is not safe for further work.
        """
        nonce = uuid.uuid4().hex
        result = get_freecad_connection().check_rpc_sync(nonce)
        if result.get("success") and result.get("nonce") == nonce:
            return json_response({"ok": True, "synchronized": True, "nonce": nonce})
        if result.get("success") and result.get("nonce") != nonce:
            details = {
                "ok": False,
                "synchronized": False,
                "expected_nonce": nonce,
                "rpc_result": result,
            }
            return tool_fail(
                "FreeCAD GUI-RPC synchronization nonce did not match this call",
                structured=details,
                error_code="NONCE_MISMATCH",
            )
        if not isinstance(result, dict) or "success" not in result:
            return tool_fail(
                "FreeCAD GUI-RPC synchronization returned a malformed response",
                structured={"rpc_result": result},
                error_code="MALFORMED_RESPONSE",
            )
        details = {
            "ok": False,
            "synchronized": False,
            "expected_nonce": nonce,
            "rpc_result": result,
        }
        return json_response(
            details,
            status=OutcomeStatus.CONDITION_FALSE,
            message="FreeCAD GUI-RPC queue is currently not synchronized",
        )

    exports['check_rpc_sync'] = check_rpc_sync
def _register_get_request_status(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def get_request_status(ctx: Context, request_id: str) -> CallToolResult:
        """Query a timed-out or long-running authenticated request without replaying it."""

        try:
            result = get_freecad_connection().get_request_status(request_id)
        except Exception as exc:
            return tool_fail(
                f"Failed to query request status: {exc}",
                error_code=getattr(exc, "code", type(exc).__name__.upper()),
            )
        state_value = str(result.get("state") or "unknown")
        status = (
            OutcomeStatus.CONDITION_FALSE
            if result.get("success") and state_value in {"unknown", "expired"}
            else None
        )
        return json_response(
            result,
            status=status,
            message=f"Request {request_id}: {state_value}",
        )

    exports['get_request_status'] = get_request_status
def _register_claim_acquisition_result(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def claim_acquisition_result(ctx: Context, request_id: str) -> CallToolResult:
        """Custody a lost or pending acquire/adopt/create lease credential.

        Call after ``get_request_status`` reports ``result_claimable`` (for example
        following an automatic ``LOCKED_ERROR_HANDOFF_PENDING`` handoff or a
        transport-lost acquisition). This MCP process retains the one-time token;
        the tool result never includes the raw credential secret.
        """

        return claim_acquisition_result_operation(
            get_freecad_connection(),
            request_id=request_id,
            lease_manager=state.lease_manager,
            document_sessions=state.document_sessions,
            store_token=state.lease_tokens,
        )

    exports['claim_acquisition_result'] = claim_acquisition_result
def _register_cancel_request(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def cancel_request(ctx: Context, request_id: str) -> CallToolResult:
        """Request cooperative cancellation for an authenticated RPC request."""

        try:
            result = get_freecad_connection().cancel_request(request_id)
        except Exception as exc:
            return tool_fail(
                f"Failed to cancel request: {exc}",
                error_code=getattr(exc, "code", type(exc).__name__.upper()),
            )
        if result.get("success"):
            cancellation = result.get("cancellation") or {}
            return json_response(
                result,
                message=(
                    f"Cancellation {cancellation.get('status', 'requested')} "
                    f"for request {request_id}"
                ),
            )
        return tool_fail(
            str(result.get("error") or "Request cancellation failed"),
            structured=result,
            error_code=result.get("error_code"),
        )

    exports['cancel_request'] = cancel_request

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register runtime_control MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_check_rpc_sync(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_get_request_status(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_claim_acquisition_result(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_cancel_request(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
