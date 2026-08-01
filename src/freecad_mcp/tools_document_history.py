"""MCP tool registration — document history (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    close_document_operation,
    get_recompute_log_operation,
    recompute_document_operation,
    redo_operation,
    undo_operation,
)
from .tools_server_surfaces import server_connection

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_recompute_document(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def recompute_document(ctx: Context, doc_name: str) -> CallToolResult:
        """Force FreeCAD to recompute all objects in a document.

        Useful after a sequence of property edits that did not trigger an automatic
        recompute, or after resolving a dependency cycle.

        Args:
            doc_name: The document to recompute.

        Returns:
            A message indicating success or failure.
        """
        return recompute_document_operation(server_connection(), doc_name)

    exports['recompute_document'] = recompute_document
def _register_undo(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def undo(ctx: Context, doc_name: str) -> CallToolResult:
        """Undo the last operation in a FreeCAD document.

        Args:
            doc_name: The document to undo in.

        Returns:
            A message indicating success or failure.
        """
        return undo_operation(server_connection(), doc_name)

    exports['undo'] = undo
def _register_redo(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def redo(ctx: Context, doc_name: str) -> CallToolResult:
        """Redo the previously undone operation in a FreeCAD document.

        Args:
            doc_name: The document to redo in.

        Returns:
            A message indicating success or failure.
        """
        return redo_operation(server_connection(), doc_name)

    exports['redo'] = redo
def _register_get_recompute_log(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def get_recompute_log(ctx: Context, doc_name: str) -> CallToolResult:
        """Return the recompute state of every object in a document.

        Use this after a failed pad/pocket/pattern to find out which object is
        'Invalid' or 'Error' without triggering a full recompute. This is a
        cheap read-only query.

        Args:
            doc_name: The document to inspect.

        Returns:
            JSON list of objects with their name, label, TypeId, state flags,
            and a 'valid' boolean. Objects with state 'Invalid' or 'Error'
            are highlighted so you know exactly what needs fixing.

        Examples:
            ```json
            {"doc_name": "Part"}
            ```
        """
        return get_recompute_log_operation(server_connection(), doc_name)

    exports['get_recompute_log'] = get_recompute_log
def _register_close_document(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def close_document(ctx: Context, doc_name: str) -> CallToolResult:
        """Close an open FreeCAD document and free its memory.

        Use this for session hygiene when a document is no longer needed.
        Unsaved changes will be lost. Under a document lease, use
        ``finalize_document_edit`` for verified save and release before closing.

        Args:
            doc_name: The document to close.

        Returns:
            A message indicating success or failure.

        Examples:
            ```json
            {"doc_name": "Part"}
            ```
        """
        return close_document_operation(server_connection(), doc_name)

    exports['close_document'] = close_document

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register document_history MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_recompute_document(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_undo(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_redo(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_get_recompute_log(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_close_document(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
