# ruff: noqa: E501
"""MCP tool registration — sketch create 1 (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    sketch_add_constraint_operation,
    sketch_add_geometry_operation,
    sketch_create_operation,
)
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_sketch_create(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_create(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        body_name: str | None = None,
        attach_to: str | None = None,
    ) -> CallToolResult:
        """Create a new Sketcher sketch in FreeCAD.

        Args:
            doc_name: The document to create the sketch in.
            sketch_name: Name for the new sketch object.
            body_name: Optional PartDesign Body to attach the sketch to. If omitted the
                sketch is added directly to the document.
            attach_to: Optional attachment target. Accepted values:
                - "XY_Plane", "XZ_Plane", "YZ_Plane" — attach to a coordinate plane.
                - "ObjectName:FaceN" — attach to a specific face of an existing object
                  (e.g. "Box:Face1").

        Returns:
            A message indicating success or failure and a screenshot.

        Recipe (avoid the silent P3 trap):
          Prefer ``attach_to`` an origin plane ("XY_Plane"/"XZ_Plane"/"YZ_Plane")
          and use ``AttachmentOffset`` to position the sketch, rather than creating
          a sketch on a default axis and then rotating its Placement. A rotated
          "Deactivated" attachment can drop the rotation (P3). For cross-body
          supports, keep the source body at an identity placement (P1) and verify
          with ``preview_attachment``.

        Examples:
            Create a sketch on the XY plane inside a Body:
            ```json
            {"doc_name": "Part", "sketch_name": "Sketch", "body_name": "Body", "attach_to": "XY_Plane"}
            ```

            Create a standalone sketch on Face1 of Box:
            ```json
            {"doc_name": "Part", "sketch_name": "Sketch", "attach_to": "Box:Face1"}
            ```
        """
        return sketch_create_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            body_name,
            attach_to,
        )

    exports['sketch_create'] = sketch_create
def _register_sketch_add_geometry(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_add_geometry(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        geometry: list[dict[str, Any]],
    ) -> CallToolResult:
        """Add geometry elements to an existing Sketcher sketch.

        Each element in `geometry` is a dict with a "type" key. Supported types:

        - **line**: `{"type": "line", "start": {"x": 0, "y": 0}, "end": {"x": 10, "y": 0}}`
        - **circle**: `{"type": "circle", "center": {"x": 0, "y": 0}, "radius": 5}`
        - **arc**: `{"type": "arc", "center": {"x": 0, "y": 0}, "radius": 5,
          "start_angle": 0, "end_angle": 90}`
          (angles in degrees, counter-clockwise)
        - **rectangle**: `{"type": "rectangle", "x1": 0, "y1": 0, "x2": 10, "y2": 10}`
          (expands to 4 connected line segments)
        - **point**: `{"type": "point", "x": 5, "y": 5}`

        All geometry can carry an optional `"construction": true` key to mark it as a
        construction (helper) line.

        Args:
            doc_name: The document containing the sketch.
            sketch_name: Name of the target sketch.
            geometry: List of geometry descriptors (see above).

        Returns:
            A message with the assigned geometry indices and a screenshot.

        Examples:
            Add a 20x10 rectangle and a circle of radius 3:
            ```json
            {
              "doc_name": "Part",
              "sketch_name": "Sketch",
              "geometry": [
                {"type": "rectangle", "x1": -10, "y1": -5, "x2": 10, "y2": 5},
                {"type": "circle", "center": {"x": 0, "y": 0}, "radius": 3}
              ]
            }
            ```
        """
        return sketch_add_geometry_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            geometry,
        )

    exports['sketch_add_geometry'] = sketch_add_geometry
def _register_sketch_add_constraint(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_add_constraint(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        constraints: list[dict[str, Any]],
    ) -> CallToolResult:
        """Add constraints to an existing Sketcher sketch.

        Each constraint is a dict with a "type" key. Geometry indices refer to the
        order in which geometry was added (0-based). Point positions: 1 = start,
        2 = end, 3 = centre (circles/arcs).

        Supported constraint types and required keys:

        | type | keys |
        |------|------|
        | Coincident | geo1, pos1, geo2, pos2 |
        | Horizontal | geo |
        | Vertical | geo |
        | Distance | geo, value  **or**  geo1, pos1, geo2, pos2, value |
        | DistanceX | geo, value  **or**  geo, pos, value |
        | DistanceY | geo, value  **or**  geo, pos, value |
        | Radius | geo, value |
        | Diameter | geo, value |
        | Angle | geo, value  **or**  geo1, pos1, geo2, pos2, value |
        | Parallel | geo1, geo2 |
        | Perpendicular | geo1, geo2 |
        | Equal | geo1, geo2 |
        | Tangent | geo1, geo2 |
        | PointOnObject | geo1, pos1, geo2 |
        | Symmetric | geo1, pos1, geo2, pos2, geo3 |
        | Block | geo |

        Optional key on any dimensional constraint: ``name`` — stable identity for
        later ``sketch_edit_constraint`` / expression binding (prefer over geo index
        after trim/fillet).

        Args:
            doc_name: The document containing the sketch.
            sketch_name: Name of the target sketch.
            constraints: List of constraint descriptors (see table above).

        Returns:
            A message indicating success or failure and a screenshot.

        Examples:
            Constrain a rectangle at the origin with width=20, height=10:
            ```json
            {
              "doc_name": "Part",
              "sketch_name": "Sketch",
              "constraints": [
                {"type": "Coincident", "geo1": 0, "pos1": 1, "geo2": -1, "pos2": 1},
                {"type": "Horizontal", "geo": 0},
                {"type": "Horizontal", "geo": 2},
                {"type": "Vertical", "geo": 1},
                {"type": "Vertical", "geo": 3},
                {"type": "Distance", "geo": 0, "value": 20},
                {"type": "Distance", "geo": 1, "value": 10}
              ]
            }
            ```
        """
        return sketch_add_constraint_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            constraints,
        )

    exports['sketch_add_constraint'] = sketch_add_constraint

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register sketch_create_1 MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_sketch_create(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_sketch_add_geometry(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_sketch_add_constraint(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
