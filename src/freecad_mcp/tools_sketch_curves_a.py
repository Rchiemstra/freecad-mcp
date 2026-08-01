"""MCP tool registration — sketch curves a (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    sketch_add_bezier_operation,
    sketch_add_bspline_operation,
    sketch_add_bspline_through_points_operation,
    sketch_add_polyline_operation,
)
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_sketch_add_polyline(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_add_polyline(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        points: list[dict[str, float]],
        closed: bool = False,
        construction: bool = False,
    ) -> CallToolResult:
        """Add a polyline (connected line segments) to a sketch.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            points: List of ``{"x": …, "y": …}`` dicts.
            closed: If true, close the polyline back to the first point.
            construction: If true, add all segments as construction lines.

        Returns:
            Success message with assigned geometry indices and a screenshot.
        """
        return sketch_add_polyline_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            points,
            closed,
            construction,
        )

    exports['sketch_add_polyline'] = sketch_add_polyline
def _register_sketch_add_bspline(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_add_bspline(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        poles: list[dict[str, float]],
        degree: int = 3,
        weights: list[float] | None = None,
        knots: list[float] | None = None,
        multiplicities: list[int] | None = None,
        periodic: bool = False,
        construction: bool = False,
    ) -> CallToolResult:
        """Add a B-spline defined by control points (poles) to a sketch.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            poles: Control points as ``{"x": …, "y": …}`` dicts.
            degree: Polynomial degree (default 3 = cubic).
            weights: Optional rational weights (uniform if omitted).
            knots: Optional knot vector.
            multiplicities: Optional knot multiplicities.
            periodic: If true, generate a closed periodic spline.
            construction: If true, add as a construction curve.

        Returns:
            Success message with the assigned geometry index and a screenshot.
        """
        return sketch_add_bspline_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            poles,
            degree,
            weights,
            knots,
            multiplicities,
            periodic,
            construction,
        )

    exports['sketch_add_bspline'] = sketch_add_bspline
def _register_sketch_add_bspline_through_points(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_add_bspline_through_points(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        points: list[dict[str, float]],
        degree: int = 3,
        periodic: bool = False,
        construction: bool = False,
    ) -> CallToolResult:
        """Add a B-spline that interpolates (passes through) a set of points.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            points: Points to interpolate as ``{"x": …, "y": …}`` dicts.
            degree: Polynomial degree (default 3).
            periodic: If true, close the spline back to the first point.
            construction: If true, add as a construction curve.

        Returns:
            Success message with the assigned geometry index and a screenshot.
        """
        return sketch_add_bspline_through_points_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            points,
            degree,
            periodic,
            construction,
        )

    exports['sketch_add_bspline_through_points'] = sketch_add_bspline_through_points
def _register_sketch_add_bezier(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_add_bezier(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        poles: list[dict[str, float]],
        construction: bool = False,
    ) -> CallToolResult:
        """Add a Bezier curve defined by control poles to a sketch.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            poles: Control points as ``{"x": …, "y": …}`` dicts.
                Degree = len(poles) - 1.
            construction: If true, add as a construction curve.

        Returns:
            Success message with the assigned geometry index and a screenshot.
        """
        return sketch_add_bezier_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            poles,
            construction,
        )

    exports['sketch_add_bezier'] = sketch_add_bezier

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register sketch_curves_a MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_sketch_add_polyline(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_sketch_add_bspline(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_sketch_add_bspline_through_points(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_sketch_add_bezier(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
