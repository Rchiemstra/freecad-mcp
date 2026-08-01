"""MCP tool registration — io import (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    import_brep_operation,
    import_step_operation,
)
from .tools_server_surfaces import server_connection

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_import_step(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def import_step(
        ctx: Context,
        doc_name: str,
        file_path: str,
    ) -> CallToolResult:
        """Import a STEP file into an existing FreeCAD document.

        Args:
            doc_name: Target document name.
            file_path: Absolute path to the STEP file to import.

        Returns:
            JSON confirming success and the file path.
        """
        return import_step_operation(server_connection(), doc_name, file_path)

    exports['import_step'] = import_step
def _register_import_brep(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def import_brep(
        ctx: Context,
        doc_name: str,
        file_path: str,
        obj_name: str = "BRepImport",
    ) -> CallToolResult:
        """Import a BREP file into an existing FreeCAD document.

        Args:
            doc_name: Target document name.
            file_path: Absolute path to the BREP file to import.
            obj_name: Name for the imported Part::Feature object.

        Returns:
            JSON confirming success and the object name.
        """
        return import_brep_operation(
            server_connection(), doc_name, file_path, obj_name
        )

    exports['import_brep'] = import_brep

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register io_import MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_import_step(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_import_brep(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
