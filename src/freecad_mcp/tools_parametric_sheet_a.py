"""MCP tool registration — parametric sheet a (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    spreadsheet_create_operation,
    spreadsheet_get_cells_operation,
    spreadsheet_set_alias_operation,
    spreadsheet_set_cells_operation,
)
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_spreadsheet_create(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def spreadsheet_create(
        ctx: Context,
        doc_name: str,
        sheet_name: str,
    ) -> CallToolResult:
        """Create a Spreadsheet::Sheet for parametric dimensions.

        Recipe: create sheet → set cells/aliases → bind sketch constraints and
        Pad/Pocket Length via ``set_expression`` using ``<<Sheet>>.Alias``.

        Args:
            doc_name: Document to create the sheet in.
            sheet_name: Name for the new spreadsheet object (e.g. ``Dims``).
        """
        return spreadsheet_create_operation(
            server_connection(), server_state().only_text_feedback, doc_name, sheet_name
        )

    exports['spreadsheet_create'] = spreadsheet_create
def _register_spreadsheet_set_cells(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def spreadsheet_set_cells(
        ctx: Context,
        doc_name: str,
        sheet_name: str,
        cells: list[dict[str, Any]],
    ) -> CallToolResult:
        """Set spreadsheet cell values (and optional aliases) in batch.

        Each cell dict accepts:
        - ``address`` (e.g. ``A1``) and/or ``alias`` to resolve an existing alias
        - ``value`` — number or formula string
        - ``alias`` with ``address`` — also sets the alias on that address
        - ``set_alias`` — set alias when addressing by address alone

        Args:
            doc_name: Document containing the sheet.
            sheet_name: Spreadsheet object name.
            cells: List of cell update dicts.
        """
        return spreadsheet_set_cells_operation(
            server_connection(), server_state().only_text_feedback, doc_name, sheet_name, cells
        )

    exports['spreadsheet_set_cells'] = spreadsheet_set_cells
def _register_spreadsheet_get_cells(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def spreadsheet_get_cells(
        ctx: Context,
        doc_name: str,
        sheet_name: str,
        addresses: list[Any],
    ) -> CallToolResult:
        """Read spreadsheet cell contents and evaluated values.

        ``addresses`` entries may be address strings (``A1``) or dicts with
        ``address`` / ``alias``.
        """
        return spreadsheet_get_cells_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sheet_name,
            addresses,
        )

    exports['spreadsheet_get_cells'] = spreadsheet_get_cells
def _register_spreadsheet_set_alias(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def spreadsheet_set_alias(
        ctx: Context,
        doc_name: str,
        sheet_name: str,
        address: str,
        alias: str,
    ) -> CallToolResult:
        """Set a spreadsheet cell alias (e.g. A1 → Wall)."""
        return spreadsheet_set_alias_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sheet_name,
            address,
            alias,
        )

    exports['spreadsheet_set_alias'] = spreadsheet_set_alias

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register parametric_sheet_a MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_spreadsheet_create(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_spreadsheet_set_cells(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_spreadsheet_get_cells(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_spreadsheet_set_alias(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
