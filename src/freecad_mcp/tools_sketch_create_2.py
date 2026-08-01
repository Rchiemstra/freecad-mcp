"""MCP tool registration — sketch create 2 (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    sketch_delete_constraint_operation,
    sketch_delete_geometry_operation,
)
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_sketch_delete_constraint(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_delete_constraint(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        constraint_indices: list[int] | None = None,
        constraint_names: list[str] | None = None,
    ) -> CallToolResult:
        """Delete one or more constraints from a Sketcher sketch.

        All selectors are resolved and validated before the sketch changes. The
        selected constraints are then deleted in one transaction, so constraint
        indices cannot shift between deletions. Names and indices may be combined;
        duplicate selections are deleted only once.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            constraint_indices: Zero-based constraint indices to delete.
            constraint_names: Stable constraint names to delete.

        Returns:
            Deleted constraint descriptors and the remaining constraint count.
        """
        return sketch_delete_constraint_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            constraint_indices=constraint_indices,
            constraint_names=constraint_names,
        )

    exports['sketch_delete_constraint'] = sketch_delete_constraint
def _register_sketch_delete_geometry(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_delete_geometry(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        geometry_indices: list[int],
    ) -> CallToolResult:
        """Delete one or more geometry items from a Sketcher sketch.

        Geometry indices are zero-based and are validated before mutation. FreeCAD
        also removes constraints that depend on deleted geometry; the result
        reports how many dependent constraints were removed.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            geometry_indices: Non-empty list of zero-based geometry indices.

        Returns:
            Deleted geometry descriptors, remaining counts, and the number of
            dependent constraints removed by FreeCAD.
        """
        return sketch_delete_geometry_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            geometry_indices,
        )

    exports['sketch_delete_geometry'] = sketch_delete_geometry

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register sketch_create_2 MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_sketch_delete_constraint(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_sketch_delete_geometry(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
