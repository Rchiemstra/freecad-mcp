"""MCP tool registration — partdesign b2 (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    create_placement_binder_operation,
    create_placement_datum_operation,
    edge_axis_operation,
    placement_audit_operation,
)
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_edge_axis(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def edge_axis(
        ctx: Context, doc_name: str, object_name: str, edge: str
    ) -> CallToolResult:
        """Return the global axis/direction (and centre) of an edge (M6 / P8 guard).

        Derives the vector from the curve geometry rotated by the object's global
        placement. Returns JSON
        ``{ok, object, subshape, type, global_center, global_normal, radius}``.

        Args:
            doc_name: The document containing the object.
            object_name: The object whose edge to inspect.
            edge: The edge name, e.g. ``"Edge2"``.
        """
        return edge_axis_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            object_name,
            edge,
        )

    exports['edge_axis'] = edge_axis
def _register_placement_audit(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def placement_audit(ctx: Context, doc_name: str) -> CallToolResult:
        """Audit placements per Body/Part (M3).

        Lists each Body/Part's ``Placement``, ``getGlobalPlacement()`` base, and the
        cross-body datums that reference it. Use to spot P1 risk concentrations and
        placement/geometry disagreements. Returns JSON
        ``{ok, doc, bodies: [{name, type, placement_base, placement_rotation,
        global_placement_base, cross_body_datums}]}``.

        Args:
            doc_name: The document to audit.
        """
        return placement_audit_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
        )

    exports['placement_audit'] = placement_audit
def _register_create_placement_binder(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def create_placement_binder(
        ctx: Context,
        doc_name: str,
        owner_body: str,
        name: str,
        source: str,
        relative: bool = True,
        bind_mode: str = "Synchronized",
    ) -> CallToolResult:
        """Create a SubShapeBinder using a body subpath with placement diagnostics (M6).

        ``source`` should be a body subpath such as ``MG996RHornRef.HornHubPad.Face3``.
        Returns resolved source/binder local and global centers/normals and whether
        parent-body placement was dropped.
        """
        return create_placement_binder_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            owner_body,
            name,
            source,
            relative=relative,
            bind_mode=bind_mode,
        )

    exports['create_placement_binder'] = create_placement_binder
def _register_create_placement_datum(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def create_placement_datum(
        ctx: Context,
        doc_name: str,
        owner_body: str,
        name: str,
        source: str,
        relative: bool = True,
        offset: list[float] | None = None,
    ) -> CallToolResult:
        """Create a datum plane from a body subpath with local/global diagnostics (M6)."""
        return create_placement_datum_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            owner_body,
            name,
            source,
            relative=relative,
            offset=offset,
        )

    exports['create_placement_datum'] = create_placement_datum

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register partdesign_b2 MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_edge_axis(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_placement_audit(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_create_placement_binder(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_create_placement_datum(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
