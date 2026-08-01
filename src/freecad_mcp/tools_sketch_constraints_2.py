"""MCP tool registration — sketch constraints 2 (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    sketch_constrain_equal_operation,
    sketch_constrain_parallel_operation,
    sketch_constrain_perpendicular_operation,
    sketch_constrain_tangent_operation,
)
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_sketch_constrain_equal(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_constrain_equal(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        geo1: int,
        geo2: int,
    ) -> CallToolResult:
        """Constrain two geometry elements to have equal length or radius.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            geo1: Index of the first geometry element.
            geo2: Index of the second geometry element.

        Returns:
            Success message and a screenshot.
        """
        return sketch_constrain_equal_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            geo1,
            geo2,
        )

    exports['sketch_constrain_equal'] = sketch_constrain_equal
def _register_sketch_constrain_parallel(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_constrain_parallel(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        geo1: int,
        geo2: int,
    ) -> CallToolResult:
        """Constrain two lines to be parallel.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            geo1: Index of the first line.
            geo2: Index of the second line.

        Returns:
            Success message and a screenshot.
        """
        return sketch_constrain_parallel_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            geo1,
            geo2,
        )

    exports['sketch_constrain_parallel'] = sketch_constrain_parallel
def _register_sketch_constrain_perpendicular(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_constrain_perpendicular(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        geo1: int,
        geo2: int,
    ) -> CallToolResult:
        """Constrain two lines to be perpendicular (90°).

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            geo1: Index of the first line.
            geo2: Index of the second line.

        Returns:
            Success message and a screenshot.
        """
        return sketch_constrain_perpendicular_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            geo1,
            geo2,
        )

    exports['sketch_constrain_perpendicular'] = sketch_constrain_perpendicular
def _register_sketch_constrain_tangent(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_constrain_tangent(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        geo1: int,
        geo2: int,
    ) -> CallToolResult:
        """Constrain two curves (or a curve and a line) to be tangent.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            geo1: Index of the first geometry element.
            geo2: Index of the second geometry element.

        Returns:
            Success message and a screenshot.
        """
        return sketch_constrain_tangent_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            geo1,
            geo2,
        )

    exports['sketch_constrain_tangent'] = sketch_constrain_tangent

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register sketch_constraints_2 MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_sketch_constrain_equal(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_sketch_constrain_parallel(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_sketch_constrain_perpendicular(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_sketch_constrain_tangent(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
