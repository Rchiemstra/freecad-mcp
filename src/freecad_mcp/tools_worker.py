"""MCP tool registration — worker (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .responses import json_response, tool_fail
from .tools_server_surfaces import server_connection

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_get_worker_status(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def get_worker_status(ctx: Context) -> CallToolResult:
        """Report isolated FreeCADCmd availability and whether a worker job is active.

        Returns JSON with:
        - ``state``: ``idle`` | ``busy`` | ``unavailable``
        - ``busy``: true while a FreeCADCmd job is running
        - ``active_job_id`` / ``pending_job_ids`` / ``queue_depth``
        - ``available``, ``version``, ``executable``, ``last_error``
        """
        try:
            return json_response(server_connection().get_worker_status())
        except Exception as exc:
            return tool_fail(f"Failed to get worker status: {exc}")

    exports['get_worker_status'] = get_worker_status
def _register_cancel_worker_job(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def cancel_worker_job(ctx: Context, job_id: str) -> CallToolResult:
        """Cancel a pending worker job or terminate the active worker process tree."""
        try:
            return json_response(server_connection().cancel_worker_job(job_id))
        except Exception as exc:
            return tool_fail(f"Failed to cancel worker job: {exc}")

    exports['cancel_worker_job'] = cancel_worker_job

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register worker MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_get_worker_status(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_cancel_worker_job(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
