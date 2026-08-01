"""MCP tool registration — sketch curves a2 (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    sketch_add_arc_of_ellipse_operation,
    sketch_add_ellipse_operation,
    sketch_add_slot_operation,
)
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_sketch_add_ellipse(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_add_ellipse(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        cx: float,
        cy: float,
        major_radius: float,
        minor_radius: float,
        angle: float = 0.0,
        construction: bool = False,
    ) -> CallToolResult:
        """Add a full ellipse to a sketch.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            cx: X coordinate of ellipse centre.
            cy: Y coordinate of ellipse centre.
            major_radius: Semi-major axis length in mm.
            minor_radius: Semi-minor axis length in mm.
            angle: Rotation of the major axis from the X axis, in degrees.
            construction: If true, add as a construction ellipse.

        Returns:
            Success message with the assigned geometry index and a screenshot.
        """
        return sketch_add_ellipse_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            cx,
            cy,
            major_radius,
            minor_radius,
            angle,
            construction,
        )

    exports['sketch_add_ellipse'] = sketch_add_ellipse
def _register_sketch_add_arc_of_ellipse(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_add_arc_of_ellipse(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        cx: float,
        cy: float,
        major_radius: float,
        minor_radius: float,
        start_angle: float,
        end_angle: float,
        angle: float = 0.0,
        construction: bool = False,
    ) -> CallToolResult:
        """Add an arc of an ellipse to a sketch.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            cx: X coordinate of ellipse centre.
            cy: Y coordinate of ellipse centre.
            major_radius: Semi-major axis length in mm.
            minor_radius: Semi-minor axis length in mm.
            start_angle: Start angle on the ellipse in degrees.
            end_angle: End angle on the ellipse in degrees.
            angle: Rotation of major axis from X axis in degrees.
            construction: If true, add as a construction arc.

        Returns:
            Success message with the assigned geometry index and a screenshot.
        """
        return sketch_add_arc_of_ellipse_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            cx,
            cy,
            major_radius,
            minor_radius,
            start_angle,
            end_angle,
            angle,
            construction,
        )

    exports['sketch_add_arc_of_ellipse'] = sketch_add_arc_of_ellipse
def _register_sketch_add_slot(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_add_slot(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        width: float,
        construction: bool = False,
    ) -> CallToolResult:
        """Add a slot (oblong) shape to a sketch.

        The slot is defined by its two end-cap centres (x1,y1) and (x2,y2) and
        a total width (diameter of end caps).

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            x1: X of the left end-cap centre.
            y1: Y of the left end-cap centre.
            x2: X of the right end-cap centre.
            y2: Y of the right end-cap centre.
            width: Total width of the slot (diameter of end caps) in mm.
            construction: If true, add all geometry as construction lines.

        Returns:
            Success message with 4 geometry indices (2 lines + 2 arcs).
        """
        return sketch_add_slot_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            x1,
            y1,
            x2,
            y2,
            width,
            construction,
        )

    exports['sketch_add_slot'] = sketch_add_slot

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register sketch_curves_a2 MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_sketch_add_ellipse(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_sketch_add_arc_of_ellipse(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_sketch_add_slot(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
