"""MCP tool registration — sketch constraints 1 (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    sketch_constrain_coincident_operation,
    sketch_constrain_distance_operation,
    sketch_constrain_horizontal_operation,
    sketch_constrain_radius_operation,
    sketch_constrain_vertical_operation,
)
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_sketch_constrain_coincident(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_constrain_coincident(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        geo1: int,
        pos1: int,
        geo2: int,
        pos2: int,
    ) -> CallToolResult:
        """Constrain two sketch points to be coincident (share the same position).

        Point positions: 1 = start/first endpoint, 2 = end/second endpoint,
        3 = centre (circles/arcs). Use index -1 for the sketch origin point,
        -2 for a point on the Y axis, -3 for a point on the X axis.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            geo1: Index of the first geometry element.
            pos1: Point position on geo1 (1, 2, or 3).
            geo2: Index of the second geometry element.
            pos2: Point position on geo2 (1, 2, or 3).

        Returns:
            Success message and a screenshot.
        """
        return sketch_constrain_coincident_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            geo1,
            pos1,
            geo2,
            pos2,
        )

    exports['sketch_constrain_coincident'] = sketch_constrain_coincident
def _register_sketch_constrain_horizontal(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_constrain_horizontal(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        geo: int,
    ) -> CallToolResult:
        """Constrain a line to be horizontal.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            geo: Index of the line geometry element.

        Returns:
            Success message and a screenshot.
        """
        return sketch_constrain_horizontal_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            geo,
        )

    exports['sketch_constrain_horizontal'] = sketch_constrain_horizontal
def _register_sketch_constrain_vertical(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_constrain_vertical(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        geo: int,
    ) -> CallToolResult:
        """Constrain a line to be vertical.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            geo: Index of the line geometry element.

        Returns:
            Success message and a screenshot.
        """
        return sketch_constrain_vertical_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            geo,
        )

    exports['sketch_constrain_vertical'] = sketch_constrain_vertical
def _register_sketch_constrain_distance(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_constrain_distance(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        geo: int,
        value: float,
        pos: int | None = None,
        name: str | None = None,
    ) -> CallToolResult:
        """Add a distance (length) constraint to a line or between two points.

        For a line, omit `pos` to constrain its full length.
        To constrain the distance from a specific point to the origin, provide
        `pos` (1 = start point, 2 = end point).

        Prefer `name` over geo index for later edits (geo indices shift after
        trim/fillet). Use `sketch_edit_constraint(name=...)` to change the value.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            geo: Index of the geometry element.
            value: Required distance in mm.
            pos: Optional point position (1 or 2) for point-to-origin distance.
            name: Optional stable constraint name (recommended for parametric edits).

        Returns:
            Success message and a screenshot.
        """
        return sketch_constrain_distance_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            geo,
            value,
            pos,
            name,
        )

    exports['sketch_constrain_distance'] = sketch_constrain_distance
def _register_sketch_constrain_radius(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_constrain_radius(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        geo: int,
        value: float,
        name: str | None = None,
    ) -> CallToolResult:
        """Constrain the radius of a circle or arc.

        Prefer `name` over geo index for later edits. Bind live values with
        `set_expression` on `Constraints[i]` or edit via `sketch_edit_constraint`.

        Args:
            doc_name: Document containing the sketch.
            sketch_name: Name of the target sketch.
            geo: Index of the circle or arc geometry element.
            value: Required radius in mm.
            name: Optional stable constraint name (recommended for parametric edits).

        Returns:
            Success message and a screenshot.
        """
        return sketch_constrain_radius_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            geo,
            value,
            name,
        )

    exports['sketch_constrain_radius'] = sketch_constrain_radius

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register sketch_constraints_1 MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_sketch_constrain_coincident(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_sketch_constrain_horizontal(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_sketch_constrain_vertical(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_sketch_constrain_distance(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_sketch_constrain_radius(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
