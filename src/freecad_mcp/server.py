import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ImageContent, TextContent

from .freecad_client import FreeCADConnection
from .operations import (
    # Core
    close_document_operation,
    create_document_operation,
    create_object_operation,
    delete_object_operation,
    edit_object_operation,
    execute_code_operation,
    get_object_operation,
    get_objects_operation,
    get_parts_list_operation,
    get_recompute_log_operation,
    get_sketch_diagnostics_operation,
    get_view_operation,
    insert_part_from_library_operation,
    list_documents_operation,
    sketch_create_operation,
    sketch_add_geometry_operation,
    sketch_add_constraint_operation,
    sketch_add_line_operation,
    sketch_add_circle_operation,
    sketch_add_arc_operation,
    sketch_add_rectangle_operation,
    sketch_constrain_coincident_operation,
    sketch_constrain_horizontal_operation,
    sketch_constrain_vertical_operation,
    sketch_constrain_distance_operation,
    sketch_constrain_radius_operation,
    sketch_constrain_equal_operation,
    sketch_constrain_parallel_operation,
    sketch_constrain_perpendicular_operation,
    sketch_constrain_tangent_operation,
    pad_feature_operation,
    pocket_feature_operation,
    linear_pattern_feature_operation,
    polar_pattern_feature_operation,
    mirror_feature_operation,
    create_spur_gear_operation,
    recompute_document_operation,
    undo_operation,
    redo_operation,
    # P1 — Sketch curves
    sketch_add_polyline_operation,
    sketch_add_bspline_operation,
    sketch_add_bspline_through_points_operation,
    sketch_add_bezier_operation,
    sketch_add_ellipse_operation,
    sketch_add_arc_of_ellipse_operation,
    sketch_add_slot_operation,
    sketch_add_regular_polygon_operation,
    sketch_add_parametric_curve_operation,
    sketch_import_points_operation,
    sketch_toggle_construction_operation,
    # P2 — Sketch editing
    sketch_trim_operation,
    sketch_extend_operation,
    sketch_split_operation,
    sketch_fillet_operation,
    sketch_offset_operation,
    sketch_symmetry_operation,
    # P3 — 3-D features
    revolve_feature_operation,
    loft_feature_operation,
    sweep_feature_operation,
    helical_sweep_feature_operation,
    fillet_feature_operation,
    chamfer_feature_operation,
    boolean_union_operation,
    boolean_difference_operation,
    boolean_intersection_operation,
    # P4 — Gear library
    create_involute_gear_operation,
    create_helical_gear_operation,
    compute_gear_geometry_operation,
    check_gear_pair_operation,
    # P5 — Measurement & transforms
    measure_distance_operation,
    measure_angle_operation,
    measure_area_operation,
    measure_volume_operation,
    bounding_box_operation,
    center_of_mass_operation,
    validate_geometry_operation,
    translate_operation,
    rotate_operation,
    scale_operation,
    # P6 — IO
    export_step_operation,
    import_step_operation,
    export_stl_operation,
    export_brep_operation,
    import_brep_operation,
    set_color_operation,
    # P7 — Assembly references, sketch geometry, path wires
    build_path_wire_operation,
    create_datum_plane_operation,
    create_part_container_operation,
    create_subshape_binder_operation,
    get_document_tree_operation,
    get_sketch_geometry_operation,
    move_object_operation,
    sketch_add_external_projection_operation,
    sweep_pipe_operation,
)
from .prompt_text import ASSET_CREATION_STRATEGY
from .server_state import ServerState


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("FreeCADMCPserver")

state = ServerState()


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    try:
        logger.info("FreeCADMCP server starting up")
        # Do not connect to FreeCAD here: probing the RPC server can block for a
        # couple of seconds, which delays the MCP `initialize` handshake long
        # enough that clients with a short init timeout (e.g. the interactive
        # Cursor agent panel) mark the server as failed. The connection is
        # established lazily on first tool use via get_freecad_connection().
        logger.info("FreeCAD connection deferred until first tool use")
        yield {}
    finally:
        if state.freecad_connection:
            logger.info("Disconnecting from FreeCAD on shutdown")
            state.freecad_connection.disconnect()
            state.freecad_connection = None
        logger.info("FreeCADMCP server shut down")


mcp = FastMCP(
    "FreeCADMCP",
    instructions="FreeCAD integration through the Model Context Protocol",
    lifespan=server_lifespan,
)


def get_freecad_connection() -> FreeCADConnection:
    """Get or create a persistent FreeCAD connection"""
    if state.freecad_connection is None:
        state.freecad_connection = FreeCADConnection(host=state.rpc_host, port=9875)
        if not state.freecad_connection.ping():
            logger.error("Failed to ping FreeCAD")
            state.freecad_connection = None
            raise Exception(
                "Failed to connect to FreeCAD. Make sure the FreeCAD addon is running."
            )
    return state.freecad_connection


@mcp.tool()
def create_document(ctx: Context, name: str) -> list[TextContent]:
    """Create a new document in FreeCAD.

    Args:
        name: The name of the document to create.

    Returns:
        A message indicating the success or failure of the document creation.

    Examples:
        If you want to create a document named "MyDocument", you can use the following data.
        ```json
        {
            "name": "MyDocument"
        }
        ```
    """
    return create_document_operation(get_freecad_connection(), name)


@mcp.tool()
def create_object(
    ctx: Context,
    doc_name: str,
    obj_type: str,
    obj_name: str,
    analysis_name: str | None = None,
    obj_properties: dict[str, Any] = None,
) -> list[TextContent | ImageContent]:
    """Create a new object in FreeCAD.
    Object type is starts with "Part::" or "Draft::" or "PartDesign::" or "Fem::".

    Args:
        doc_name: The name of the document to create the object in.
        obj_type: The type of the object to create (e.g. 'Part::Box', 'Part::Cylinder', 'Draft::Circle', 'PartDesign::Body', etc.).
        obj_name: The name of the object to create.
        obj_properties: The properties of the object to create.

    Returns:
        A message indicating the success or failure of the object creation and a screenshot of the object.

    Examples:
        If you want to create a cylinder with a height of 30 and a radius of 10, you can use the following data.
        ```json
        {
            "doc_name": "MyCylinder",
            "obj_name": "Cylinder",
            "obj_type": "Part::Cylinder",
            "obj_properties": {
                "Height": 30,
                "Radius": 10,
                "Placement": {
                    "Base": {
                        "x": 10,
                        "y": 10,
                        "z": 0
                    },
                    "Rotation": {
                        "Axis": {
                            "x": 0,
                            "y": 0,
                            "z": 1
                        },
                        "Angle": 45
                    }
                },
                "ViewObject": {
                    "ShapeColor": [0.5, 0.5, 0.5, 1.0]
                }
            }
        }
        ```

        If you want to create a circle with a radius of 10, you can use the following data.
        ```json
        {
            "doc_name": "MyCircle",
            "obj_name": "Circle",
            "obj_type": "Draft::Circle",
        }
        ```

        If you want to create a FEM analysis, you can use the following data.
        ```json
        {
            "doc_name": "MyFEMAnalysis",
            "obj_name": "FemAnalysis",
            "obj_type": "Fem::AnalysisPython",
        }
        ```

        If you want to create a FEM constraint, you can use the following data.
        ```json
        {
            "doc_name": "MyFEMConstraint",
            "obj_name": "FemConstraint",
            "obj_type": "Fem::ConstraintFixed",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "References": [
                    {
                        "object_name": "MyObject",
                        "face": "Face1"
                    }
                ]
            }
        }
        ```

        If you want to create a FEM mechanical material, you can use the following data.
        ```json
        {
            "doc_name": "MyFEMAnalysis",
            "obj_name": "FemMechanicalMaterial",
            "obj_type": "Fem::MaterialCommon",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "Material": {
                    "Name": "MyMaterial",
                    "Density": "7900 kg/m^3",
                    "YoungModulus": "210 GPa",
                    "PoissonRatio": 0.3
                }
            }
        }
        ```

        If you want to create a FEM mesh, you can use the following data.
        The `Part` property is required.
        ```json
        {
            "doc_name": "MyFEMMesh",
            "obj_name": "FemMesh",
            "obj_type": "Fem::FemMeshGmsh",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "Part": "MyObject",
                "ElementSizeMax": 10,
                "ElementSizeMin": 0.1,
                "MeshAlgorithm": 2
            }
        }
        ```
    """
    return create_object_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_type,
        obj_name,
        analysis_name,
        obj_properties,
    )


@mcp.tool()
def edit_object(
    ctx: Context, doc_name: str, obj_name: str, obj_properties: dict[str, Any]
) -> list[TextContent | ImageContent]:
    """Edit an object in FreeCAD.
    This tool is used when the `create_object` tool cannot handle the object creation.

    Args:
        doc_name: The name of the document to edit the object in.
        obj_name: The name of the object to edit.
        obj_properties: The properties of the object to edit.

    Returns:
        A message indicating the success or failure of the object editing and a screenshot of the object.
    """
    return edit_object_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_name,
        obj_properties,
    )


@mcp.tool()
def delete_object(ctx: Context, doc_name: str, obj_name: str) -> list[TextContent | ImageContent]:
    """Delete an object in FreeCAD.

    Args:
        doc_name: The name of the document to delete the object from.
        obj_name: The name of the object to delete.

    Returns:
        A message indicating the success or failure of the object deletion and a screenshot of the object.
    """
    return delete_object_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_name,
    )


@mcp.tool()
def execute_code(ctx: Context, code: str) -> list[TextContent | ImageContent]:
    """Execute arbitrary Python code in FreeCAD.

    Args:
        code: The Python code to execute.

    Returns:
        A message indicating the success or failure of the code execution, the output of the code execution, and a screenshot of the object.
    """
    return execute_code_operation(get_freecad_connection(), state.only_text_feedback, code)


@mcp.tool()
def get_view(
    ctx: Context,
    view_name: Literal["Isometric", "Front", "Top", "Right", "Back", "Left", "Bottom", "Dimetric", "Trimetric"],
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
) -> list[ImageContent | TextContent]:
    """Get a screenshot of the active view.

    Args:
        view_name: The name of the view to get the screenshot of.
        The following views are available:
        - "Isometric"
        - "Front"
        - "Top"
        - "Right"
        - "Back"
        - "Left"
        - "Bottom"
        - "Dimetric"
        - "Trimetric"
        width: The width of the screenshot in pixels. If not specified, uses the viewport width.
        height: The height of the screenshot in pixels. If not specified, uses the viewport height.
        focus_object: The name of the object to focus on. If not specified, fits all objects in the view.

    Returns:
        A screenshot of the active view.
    """
    return get_view_operation(get_freecad_connection(), view_name, width, height, focus_object)


@mcp.tool()
def insert_part_from_library(ctx: Context, relative_path: str) -> list[TextContent | ImageContent]:
    """Insert a part from the parts library addon.

    Args:
        relative_path: The relative path of the part to insert.

    Returns:
        A message indicating the success or failure of the part insertion and a screenshot of the object.
    """
    return insert_part_from_library_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        relative_path,
    )


@mcp.tool()
def get_objects(ctx: Context, doc_name: str) -> list[TextContent | ImageContent]:
    """Get all objects in a document.
    You can use this tool to get the objects in a document to see what you can check or edit.

    Args:
        doc_name: The name of the document to get the objects from.

    Returns:
        A list of objects in the document and a screenshot of the document.
    """
    return get_objects_operation(get_freecad_connection(), state.only_text_feedback, doc_name)


@mcp.tool()
def get_object(ctx: Context, doc_name: str, obj_name: str) -> list[TextContent | ImageContent]:
    """Get an object from a document.
    You can use this tool to get the properties of an object to see what you can check or edit.

    Args:
        doc_name: The name of the document to get the object from.
        obj_name: The name of the object to get.

    Returns:
        The object and a screenshot of the object.
    """
    return get_object_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_name,
    )


@mcp.tool()
def get_parts_list(ctx: Context) -> list[TextContent]:
    """Get the list of parts in the parts library addon.
    """
    return get_parts_list_operation(get_freecad_connection())


@mcp.tool()
def list_documents(ctx: Context) -> list[TextContent]:
    """Get the list of open documents in FreeCAD.

    Returns:
        A list of document names.
    """
    return list_documents_operation(get_freecad_connection())


@mcp.tool()
def sketch_create(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    body_name: str | None = None,
    attach_to: str | None = None,
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        sketch_name,
        body_name,
        attach_to,
    )


@mcp.tool()
def sketch_add_geometry(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geometry: list[dict[str, Any]],
) -> list[TextContent | ImageContent]:
    """Add geometry elements to an existing Sketcher sketch.

    Each element in `geometry` is a dict with a "type" key. Supported types:

    - **line**: `{"type": "line", "start": {"x": 0, "y": 0}, "end": {"x": 10, "y": 0}}`
    - **circle**: `{"type": "circle", "center": {"x": 0, "y": 0}, "radius": 5}`
    - **arc**: `{"type": "arc", "center": {"x": 0, "y": 0}, "radius": 5, "start_angle": 0, "end_angle": 90}`
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
        Add a 20×10 rectangle and a circle of radius 3:
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
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        sketch_name,
        geometry,
    )


@mcp.tool()
def sketch_add_constraint(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    constraints: list[dict[str, Any]],
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        sketch_name,
        constraints,
    )


@mcp.tool()
def sketch_add_line(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    construction: bool = False,
) -> list[TextContent | ImageContent]:
    """Add a line segment to a sketch.

    All coordinates are in the sketch's local 2-D plane (mm).

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        x1: X coordinate of the start point.
        y1: Y coordinate of the start point.
        x2: X coordinate of the end point.
        y2: Y coordinate of the end point.
        construction: If true, add as a construction (helper) line.

    Returns:
        Success message with the assigned geometry index and a screenshot.
    """
    return sketch_add_line_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, x1, y1, x2, y2, construction,
    )


@mcp.tool()
def sketch_add_circle(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    cx: float,
    cy: float,
    radius: float,
    construction: bool = False,
) -> list[TextContent | ImageContent]:
    """Add a full circle to a sketch.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        cx: X coordinate of the centre.
        cy: Y coordinate of the centre.
        radius: Circle radius in mm.
        construction: If true, add as a construction circle.

    Returns:
        Success message with the assigned geometry index and a screenshot.
    """
    return sketch_add_circle_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, cx, cy, radius, construction,
    )


@mcp.tool()
def sketch_add_arc(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    cx: float,
    cy: float,
    radius: float,
    start_angle: float,
    end_angle: float,
    construction: bool = False,
) -> list[TextContent | ImageContent]:
    """Add a circular arc to a sketch.

    Angles are in degrees, measured counter-clockwise from the positive X axis.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        cx: X coordinate of the arc centre.
        cy: Y coordinate of the arc centre.
        radius: Arc radius in mm.
        start_angle: Start angle in degrees (0 = right, 90 = up).
        end_angle: End angle in degrees (must be > start_angle for CCW arc).
        construction: If true, add as a construction arc.

    Returns:
        Success message with the assigned geometry index and a screenshot.
    """
    return sketch_add_arc_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, cx, cy, radius, start_angle, end_angle, construction,
    )


@mcp.tool()
def sketch_add_rectangle(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    construction: bool = False,
) -> list[TextContent | ImageContent]:
    """Add an axis-aligned rectangle to a sketch (4 connected line segments).

    Returns the 4 geometry indices in order: bottom, right, top, left.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        x1: X coordinate of the first corner.
        y1: Y coordinate of the first corner.
        x2: X coordinate of the opposite corner.
        y2: Y coordinate of the opposite corner.
        construction: If true, add all edges as construction lines.

    Returns:
        Success message with the 4 assigned geometry indices and a screenshot.
    """
    return sketch_add_rectangle_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, x1, y1, x2, y2, construction,
    )


@mcp.tool()
def sketch_constrain_coincident(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo1: int,
    pos1: int,
    geo2: int,
    pos2: int,
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo1, pos1, geo2, pos2,
    )


@mcp.tool()
def sketch_constrain_horizontal(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo: int,
) -> list[TextContent | ImageContent]:
    """Constrain a line to be horizontal.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        geo: Index of the line geometry element.

    Returns:
        Success message and a screenshot.
    """
    return sketch_constrain_horizontal_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo,
    )


@mcp.tool()
def sketch_constrain_vertical(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo: int,
) -> list[TextContent | ImageContent]:
    """Constrain a line to be vertical.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        geo: Index of the line geometry element.

    Returns:
        Success message and a screenshot.
    """
    return sketch_constrain_vertical_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo,
    )


@mcp.tool()
def sketch_constrain_distance(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo: int,
    value: float,
    pos: int | None = None,
) -> list[TextContent | ImageContent]:
    """Add a distance (length) constraint to a line or between two points.

    For a line, omit `pos` to constrain its full length.
    To constrain the distance from a specific point to the origin, provide
    `pos` (1 = start point, 2 = end point).

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        geo: Index of the geometry element.
        value: Required distance in mm.
        pos: Optional point position (1 or 2) for point-to-origin distance.

    Returns:
        Success message and a screenshot.
    """
    return sketch_constrain_distance_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo, value, pos,
    )


@mcp.tool()
def sketch_constrain_radius(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo: int,
    value: float,
) -> list[TextContent | ImageContent]:
    """Constrain the radius of a circle or arc.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        geo: Index of the circle or arc geometry element.
        value: Required radius in mm.

    Returns:
        Success message and a screenshot.
    """
    return sketch_constrain_radius_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo, value,
    )


@mcp.tool()
def sketch_constrain_equal(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo1: int,
    geo2: int,
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo1, geo2,
    )


@mcp.tool()
def sketch_constrain_parallel(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo1: int,
    geo2: int,
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo1, geo2,
    )


@mcp.tool()
def sketch_constrain_perpendicular(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo1: int,
    geo2: int,
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo1, geo2,
    )


@mcp.tool()
def sketch_constrain_tangent(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo1: int,
    geo2: int,
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo1, geo2,
    )


@mcp.tool()
def pad_feature(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    pad_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
) -> list[TextContent | ImageContent]:
    """Extrude (pad) a closed sketch profile into a 3-D solid (PartDesign::Pad).

    The sketch must be closed and fully contained in a PartDesign Body for the
    result to be a valid solid. If no `body_name` is given the tool attempts to
    find the Body that owns the sketch automatically.

    Args:
        doc_name: The document containing the sketch and body.
        sketch_name: Name of the sketch to extrude.
        pad_name: Name for the resulting Pad feature.
        length: Extrusion distance in mm.
        body_name: Optional explicit PartDesign Body name.
        symmetric: If true, extrude equally in both directions (length/2 each).
        reversed_dir: If true, reverse the extrusion direction.

    Returns:
        A message indicating success or failure and an isometric screenshot.

    Examples:
        Pad "Sketch" by 15 mm inside "Body":
        ```json
        {"doc_name": "Part", "sketch_name": "Sketch", "pad_name": "Pad", "length": 15, "body_name": "Body"}
        ```
    """
    return pad_feature_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        sketch_name,
        pad_name,
        length,
        body_name,
        symmetric,
        reversed_dir,
    )


@mcp.tool()
def pocket_feature(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    pocket_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
) -> list[TextContent | ImageContent]:
    """Cut (pocket) a closed sketch profile into an existing solid (PartDesign::Pocket).

    The sketch must be closed and must lie on or inside the existing solid. If no
    `body_name` is given the tool attempts to find the Body that owns the sketch
    automatically.

    Args:
        doc_name: The document containing the sketch and body.
        sketch_name: Name of the sketch to use as the cut profile.
        pocket_name: Name for the resulting Pocket feature.
        length: Cut depth in mm.
        body_name: Optional explicit PartDesign Body name.
        symmetric: If true, cut equally in both directions.
        reversed_dir: If true, reverse the cut direction.

    Returns:
        A message indicating success or failure and an isometric screenshot.

    Examples:
        Pocket "HoleSketch" by 5 mm:
        ```json
        {"doc_name": "Part", "sketch_name": "HoleSketch", "pocket_name": "Pocket", "length": 5, "body_name": "Body"}
        ```
    """
    return pocket_feature_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        sketch_name,
        pocket_name,
        length,
        body_name,
        symmetric,
        reversed_dir,
    )


@mcp.tool()
def linear_pattern_feature(
    ctx: Context,
    doc_name: str,
    feature_name: str,
    pattern_name: str,
    length: float,
    occurrences: int,
    direction: str = "X_Axis",
    body_name: str | None = None,
    reversed_dir: bool = False,
) -> list[TextContent | ImageContent]:
    """Repeat an existing PartDesign feature along a straight direction.

    Use this after creating a sketch-based feature such as a Pad or Pocket.
    The source feature must be inside a PartDesign Body.

    Args:
        doc_name: The document containing the body and source feature.
        feature_name: Existing feature to repeat, for example `Pocket` or `Pad`.
        pattern_name: Name for the resulting LinearPattern feature.
        length: Total pattern length in mm.
        occurrences: Number of repeated instances, including the original.
        direction: Axis or reference edge. Examples: `X_Axis`, `Y_Axis`,
            `Z_Axis`, or `ObjectName:Edge1`.
        body_name: Optional explicit PartDesign Body name.
        reversed_dir: If true, reverse the pattern direction.

    Returns:
        A message indicating success or failure and an isometric screenshot.

    Examples:
        Pattern a pocket 5 times over 40 mm along X:
        ```json
        {"doc_name": "Part", "feature_name": "Pocket", "pattern_name": "PocketArray", "length": 40, "occurrences": 5}
        ```
    """
    return linear_pattern_feature_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        feature_name,
        pattern_name,
        length,
        occurrences,
        direction,
        body_name,
        reversed_dir,
    )


@mcp.tool()
def polar_pattern_feature(
    ctx: Context,
    doc_name: str,
    feature_name: str,
    pattern_name: str,
    occurrences: int,
    angle: float = 360.0,
    axis: str = "Z_Axis",
    body_name: str | None = None,
    reversed_dir: bool = False,
) -> list[TextContent | ImageContent]:
    """Repeat an existing PartDesign feature around an axis.

    Use this for circular hole patterns or radial repeats of sketch-based Pads
    and Pockets. The source feature must be inside a PartDesign Body.

    Args:
        doc_name: The document containing the body and source feature.
        feature_name: Existing feature to repeat, for example `Pocket` or `Pad`.
        pattern_name: Name for the resulting PolarPattern feature.
        occurrences: Number of repeated instances, including the original.
        angle: Total angular span in degrees. Defaults to 360.
        axis: Axis or reference edge. Examples: `Z_Axis`, `X_Axis`, or
            `ObjectName:Edge1`.
        body_name: Optional explicit PartDesign Body name.
        reversed_dir: If true, reverse the angular direction.

    Returns:
        A message indicating success or failure and an isometric screenshot.

    Examples:
        Pattern a pocket 6 times around the Z axis:
        ```json
        {"doc_name": "Part", "feature_name": "Pocket", "pattern_name": "BoltCircle", "occurrences": 6}
        ```
    """
    return polar_pattern_feature_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        feature_name,
        pattern_name,
        occurrences,
        angle,
        axis,
        body_name,
        reversed_dir,
    )


@mcp.tool()
def mirror_feature(
    ctx: Context,
    doc_name: str,
    feature_name: str,
    mirror_name: str,
    plane: str = "YZ_Plane",
    body_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Mirror an existing PartDesign feature across a plane.

    Use this after creating a sketch-based feature such as a Pad or Pocket.
    The source feature must be inside a PartDesign Body.

    Args:
        doc_name: The document containing the body and source feature.
        feature_name: Existing feature to mirror, for example `Pocket` or `Pad`.
        mirror_name: Name for the resulting Mirrored feature.
        plane: Mirror plane. Examples: `YZ_Plane`, `XZ_Plane`, `XY_Plane`,
            or `ObjectName:Face1`.
        body_name: Optional explicit PartDesign Body name.

    Returns:
        A message indicating success or failure and an isometric screenshot.

    Examples:
        Mirror a pocket across the YZ plane:
        ```json
        {"doc_name": "Part", "feature_name": "Pocket", "mirror_name": "PocketMirror", "plane": "YZ_Plane"}
        ```
    """
    return mirror_feature_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        feature_name,
        mirror_name,
        plane,
        body_name,
    )


@mcp.tool()
def create_spur_gear(
    ctx: Context,
    doc_name: str,
    gear_name: str,
    teeth: int,
    module: float,
    width: float,
    pressure_angle: float = 20.0,
    bore_diameter: float = 0.0,
    clearance: float = 0.0,
    backlash: float = 0.0,
    samples_per_flank: int = 8,
    body_name: str | None = None,
    sketch_name: str | None = None,
    tooth_profile: str = "involute",
) -> list[TextContent | ImageContent]:
    """Create a spur gear from a Sketcher tooth profile and Pad.

    This tool generates the selected tooth profile in a Sketcher sketch, adds
    practical coincident and construction-circle constraints, then creates the
    3-D solid with a PartDesign Pad. It does not require the external Gear
    workbench.

    Args:
        doc_name: The document to create the gear in.
        gear_name: Name for the resulting Pad feature.
        teeth: Number of teeth. Must be at least 3.
        module: Gear module in mm.
        width: Pad length in mm.
        pressure_angle: Involute pressure angle in degrees. Defaults to 20.
        bore_diameter: Optional center bore diameter in mm.
        clearance: Extra root clearance in mm.
        backlash: Tooth backlash in mm, applied at the pitch circle.
        samples_per_flank: Approximation samples per tooth flank/profile side.
        body_name: Optional existing PartDesign Body. If omitted, a new body is created.
        sketch_name: Optional sketch name. Defaults to `<gear_name>_Sketch`.
        tooth_profile: Tooth profile type. Supported values:
            `involute` for normal real gears, `cycloidal` for clock-like
            profiles, `trapezoid` for angled flat-sided visual gears,
            `straight` / `straight_teeth` for square radial-sided teeth,
            `circular_arc` / `novikov` for continuous circular-arc teeth, and
            `pin` / `lantern` for hub-and-pin style gears.

    Returns:
        A message indicating success or failure and an isometric screenshot.

    Examples:
        Create a 24-tooth, module 2 gear with a 6 mm bore:
        ```json
        {
          "doc_name": "GearDoc",
          "gear_name": "Gear24",
          "teeth": 24,
          "module": 2,
          "width": 10,
          "bore_diameter": 6
        }
        ```
    """
    return create_spur_gear_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        gear_name,
        teeth,
        module,
        width,
        pressure_angle,
        bore_diameter,
        clearance,
        backlash,
        samples_per_flank,
        body_name,
        sketch_name,
        tooth_profile,
    )


@mcp.tool()
def recompute_document(ctx: Context, doc_name: str) -> list[TextContent]:
    """Force FreeCAD to recompute all objects in a document.

    Useful after a sequence of property edits that did not trigger an automatic
    recompute, or after resolving a dependency cycle.

    Args:
        doc_name: The document to recompute.

    Returns:
        A message indicating success or failure.
    """
    return recompute_document_operation(get_freecad_connection(), doc_name)


@mcp.tool()
def undo(ctx: Context, doc_name: str) -> list[TextContent]:
    """Undo the last operation in a FreeCAD document.

    Args:
        doc_name: The document to undo in.

    Returns:
        A message indicating success or failure.
    """
    return undo_operation(get_freecad_connection(), doc_name)


@mcp.tool()
def redo(ctx: Context, doc_name: str) -> list[TextContent]:
    """Redo the previously undone operation in a FreeCAD document.

    Args:
        doc_name: The document to redo in.

    Returns:
        A message indicating success or failure.
    """
    return redo_operation(get_freecad_connection(), doc_name)


@mcp.tool()
def get_recompute_log(ctx: Context, doc_name: str) -> list[TextContent]:
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
    return get_recompute_log_operation(get_freecad_connection(), doc_name)


@mcp.tool()
def get_sketch_diagnostics(
    ctx: Context, doc_name: str, sketch_name: str
) -> list[TextContent]:
    """Return solver diagnostics for a Sketcher sketch.

    Call this before pad_feature to verify the sketch is fully constrained and
    closed. Returns degrees of freedom, constraint counts, conflicting /
    redundant constraint indices, solver message, and whether the sketch wire
    is closed.

    Args:
        doc_name: The document containing the sketch.
        sketch_name: Name of the sketch to inspect.

    Returns:
        JSON dict with:
        - geometry_count: number of geometry elements
        - constraint_count: number of constraints
        - state: object state flags (e.g. ['Up-to-date'])
        - conflicting_constraints: list of conflicting constraint indices
        - redundant_constraints: list of redundant constraint indices
        - malformed_constraints: list of malformed constraint indices
        - solver_message: solver status string (if available)
        - is_closed: whether the sketch wire forms a closed profile

    Examples:
        ```json
        {"doc_name": "Part", "sketch_name": "Sketch"}
        ```
    """
    return get_sketch_diagnostics_operation(
        get_freecad_connection(), doc_name, sketch_name
    )


@mcp.tool()
def close_document(ctx: Context, doc_name: str) -> list[TextContent]:
    """Close an open FreeCAD document and free its memory.

    Use this for session hygiene when a document is no longer needed.
    Unsaved changes will be lost — save first with execute_code if needed.

    Args:
        doc_name: The document to close.

    Returns:
        A message indicating success or failure.

    Examples:
        ```json
        {"doc_name": "Part"}
        ```
    """
    return close_document_operation(get_freecad_connection(), doc_name)


# =============================================================================
# P1 — Sketch curves
# =============================================================================

@mcp.tool()
def sketch_add_polyline(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    points: list[dict[str, float]],
    closed: bool = False,
    construction: bool = False,
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, points, closed, construction,
    )


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
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, poles, degree, weights, knots, multiplicities,
        periodic, construction,
    )


@mcp.tool()
def sketch_add_bspline_through_points(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    points: list[dict[str, float]],
    degree: int = 3,
    periodic: bool = False,
    construction: bool = False,
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, points, degree, periodic, construction,
    )


@mcp.tool()
def sketch_add_bezier(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    poles: list[dict[str, float]],
    construction: bool = False,
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, poles, construction,
    )


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
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, cx, cy, major_radius, minor_radius, angle, construction,
    )


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
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, cx, cy, major_radius, minor_radius,
        start_angle, end_angle, angle, construction,
    )


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
) -> list[TextContent | ImageContent]:
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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, x1, y1, x2, y2, width, construction,
    )


@mcp.tool()
def sketch_add_regular_polygon(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    cx: float,
    cy: float,
    radius: float,
    sides: int,
    angle: float = 0.0,
    construction: bool = False,
) -> list[TextContent | ImageContent]:
    """Add a regular polygon to a sketch.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        cx: X coordinate of the circumscribed circle centre.
        cy: Y coordinate of the circumscribed circle centre.
        radius: Circumradius in mm (vertex-to-centre distance).
        sides: Number of sides (minimum 3).
        angle: Rotation offset for the first vertex in degrees.
        construction: If true, add all edges as construction lines.

    Returns:
        Success message with the assigned geometry indices and a screenshot.
    """
    return sketch_add_regular_polygon_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, cx, cy, radius, sides, angle, construction,
    )


@mcp.tool()
def sketch_add_parametric_curve(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    x_expr: str,
    y_expr: str,
    t_start: float,
    t_end: float,
    samples: int = 100,
    construction: bool = False,
) -> list[TextContent | ImageContent]:
    """Add a parametric curve to a sketch by sampling Python expressions.

    The expressions ``x_expr`` and ``y_expr`` are evaluated as Python
    expressions where ``t`` is the parameter and ``math`` is available.
    The sampled points are interpolated into a B-spline and added to the
    sketch.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        x_expr: Python expression for X coordinate. Example: ``"r_b*(math.cos(t)+t*math.sin(t))"``
        y_expr: Python expression for Y coordinate. Example: ``"r_b*(math.sin(t)-t*math.cos(t))"``
        t_start: Start value of parameter t.
        t_end: End value of parameter t (must be > t_start).
        samples: Number of sample points (10–2000, default 100).
        construction: If true, add as a construction curve.

    Returns:
        Success message with the geometry index and sample count.

    Examples:
        Involute of a base circle of radius 10:
        ```json
        {
          "doc_name": "GearDoc", "sketch_name": "Sketch",
          "x_expr": "10*(math.cos(t)+t*math.sin(t))",
          "y_expr": "10*(math.sin(t)-t*math.cos(t))",
          "t_start": 0.0, "t_end": 1.5
        }
        ```
    """
    return sketch_add_parametric_curve_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, x_expr, y_expr, t_start, t_end, samples, construction,
    )


@mcp.tool()
def sketch_import_points(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    points: list[dict[str, float]],
    construction: bool = False,
) -> list[TextContent | ImageContent]:
    """Import a list of 2-D points as individual point geometry elements.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        points: List of ``{"x": …, "y": …}`` dicts.
        construction: If true, add as construction points.

    Returns:
        Success message with the assigned geometry indices.
    """
    return sketch_import_points_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, points, construction,
    )


@mcp.tool()
def sketch_toggle_construction(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo_indices: list[int],
    construction: bool = True,
) -> list[TextContent | ImageContent]:
    """Toggle one or more sketch geometry elements between normal and construction mode.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        geo_indices: List of 0-based geometry indices to toggle.
        construction: Target state — True for construction, False for normal.

    Returns:
        Success message and a screenshot.
    """
    return sketch_toggle_construction_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo_indices, construction,
    )


# =============================================================================
# P2 — Sketch editing
# =============================================================================

@mcp.tool()
def sketch_trim(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo_index: int,
    point_x: float,
    point_y: float,
) -> list[TextContent | ImageContent]:
    """Trim a sketch curve at the given point (nearest intersection).

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        geo_index: Index of the geometry element to trim.
        point_x: X coordinate on the curve near the desired cut point.
        point_y: Y coordinate on the curve near the desired cut point.

    Returns:
        Success message and a screenshot.
    """
    return sketch_trim_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo_index, point_x, point_y,
    )


@mcp.tool()
def sketch_extend(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo_index: int,
    increment: float,
    end_point: int = 2,
) -> list[TextContent | ImageContent]:
    """Extend a sketch curve by a given increment.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        geo_index: Index of the geometry element to extend.
        increment: Extension amount in mm.
        end_point: Which end to extend: 1 = start, 2 = end (default).

    Returns:
        Success message and a screenshot.
    """
    return sketch_extend_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo_index, increment, end_point,
    )


@mcp.tool()
def sketch_split(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo_index: int,
    point_x: float,
    point_y: float,
) -> list[TextContent | ImageContent]:
    """Split a sketch curve into two pieces at the given point.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        geo_index: Index of the geometry element to split.
        point_x: X coordinate of the split point.
        point_y: Y coordinate of the split point.

    Returns:
        Success message and a screenshot.
    """
    return sketch_split_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo_index, point_x, point_y,
    )


@mcp.tool()
def sketch_fillet(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo1: int,
    geo2: int,
    radius: float,
) -> list[TextContent | ImageContent]:
    """Add a fillet arc between two sketch curves.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        geo1: Index of the first geometry element.
        geo2: Index of the second geometry element.
        radius: Fillet radius in mm (must be > 0).

    Returns:
        Success message and a screenshot.
    """
    return sketch_fillet_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo1, geo2, radius,
    )


@mcp.tool()
def sketch_symmetry(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geo_indices: list[int],
    symmetry_geo: int,
    copy: bool = True,
) -> list[TextContent | ImageContent]:
    """Apply symmetry to a set of sketch elements about a symmetry axis.

    Args:
        doc_name: Document containing the sketch.
        sketch_name: Name of the target sketch.
        geo_indices: Indices of the elements to mirror.
        symmetry_geo: Index of the symmetry axis geometry element.
        copy: If true, keep the original elements (default).

    Returns:
        Success message and a screenshot.
    """
    return sketch_symmetry_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo_indices, symmetry_geo, copy,
    )


# =============================================================================
# P3 — 3-D features
# =============================================================================

@mcp.tool()
def revolve_feature(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    revolve_name: str,
    angle: float = 360.0,
    axis: str = "Z_Axis",
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
) -> list[TextContent | ImageContent]:
    """Revolve a closed sketch profile around an axis (PartDesign::Revolution).

    Args:
        doc_name: Document containing the sketch and body.
        sketch_name: Name of the sketch to revolve.
        revolve_name: Name for the resulting Revolution feature.
        angle: Revolution angle in degrees (default 360 = full solid of revolution).
        axis: Revolution axis. Examples: ``Z_Axis``, ``X_Axis``, ``ObjectName:Edge1``.
        body_name: Optional explicit PartDesign Body name.
        symmetric: If true, revolve symmetrically about the sketch plane.
        reversed_dir: If true, reverse the revolution direction.

    Returns:
        Success message and an isometric screenshot.
    """
    return revolve_feature_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, revolve_name, angle, axis, body_name, symmetric, reversed_dir,
    )


@mcp.tool()
def loft_feature(
    ctx: Context,
    doc_name: str,
    sketch_names: list[str],
    loft_name: str,
    body_name: str | None = None,
    ruled: bool = False,
    closed: bool = False,
) -> list[TextContent | ImageContent]:
    """Loft through two or more sketch sections (PartDesign::AdditiveLoft).

    Args:
        doc_name: Document containing the sketches and body.
        sketch_names: Ordered list of sketch names to loft through (minimum 2).
        loft_name: Name for the resulting Loft feature.
        body_name: Optional explicit PartDesign Body name.
        ruled: If true, use straight (ruled) lofting instead of smooth.
        closed: If true, close the loft back to the first section.

    Returns:
        Success message and an isometric screenshot.
    """
    return loft_feature_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_names, loft_name, body_name, ruled, closed,
    )


@mcp.tool()
def sweep_feature(
    ctx: Context,
    doc_name: str,
    profile_sketch: str,
    path_sketch: str,
    sweep_name: str,
    body_name: str | None = None,
    frenet: bool = False,
) -> list[TextContent | ImageContent]:
    """Sweep a profile sketch along a path sketch (PartDesign::AdditivePipe).

    Args:
        doc_name: Document containing the sketches and body.
        profile_sketch: Name of the cross-section sketch.
        path_sketch: Name of the path sketch.
        sweep_name: Name for the resulting Sweep feature.
        body_name: Optional explicit PartDesign Body name.
        frenet: If true, use Frenet-Serret frame (avoids twisting on curved paths).

    Returns:
        Success message and an isometric screenshot.
    """
    return sweep_feature_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, profile_sketch, path_sketch, sweep_name, body_name, frenet,
    )


@mcp.tool()
def helical_sweep_feature(
    ctx: Context,
    doc_name: str,
    profile_sketch: str,
    helix_name: str,
    pitch: float,
    height: float,
    radius: float,
    body_name: str | None = None,
    left_handed: bool = False,
    reversed_dir: bool = False,
) -> list[TextContent | ImageContent]:
    """Sweep a profile along a helix (PartDesign::AdditiveHelix).

    Use this to create springs, screw threads, worm gear blanks, etc.

    Args:
        doc_name: Document containing the sketch and body.
        profile_sketch: Name of the cross-section sketch.
        helix_name: Name for the resulting Helix feature.
        pitch: Distance between successive turns in mm.
        height: Total height of the helix in mm.
        radius: Helix radius in mm.
        body_name: Optional explicit PartDesign Body name.
        left_handed: If true, produce a left-handed helix.
        reversed_dir: If true, reverse the helix direction.

    Returns:
        Success message and an isometric screenshot.
    """
    return helical_sweep_feature_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, profile_sketch, helix_name, pitch, height, radius,
        body_name, left_handed, reversed_dir,
    )


@mcp.tool()
def fillet_feature(
    ctx: Context,
    doc_name: str,
    base_feature: str,
    fillet_name: str,
    radius: float,
    edge_refs: list[str] | None = None,
    body_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Add a fillet to edges of an existing solid (PartDesign::Fillet).

    Args:
        doc_name: Document containing the body and feature.
        base_feature: Name of the feature to fillet.
        fillet_name: Name for the resulting Fillet feature.
        radius: Fillet radius in mm (must be > 0).
        edge_refs: Optional list of edge references like ``["Edge1","Edge3"]``.
            If omitted, all edges are filleted.
        body_name: Optional explicit PartDesign Body name.

    Returns:
        Success message and an isometric screenshot.
    """
    return fillet_feature_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, base_feature, fillet_name, radius, edge_refs, body_name,
    )


@mcp.tool()
def chamfer_feature(
    ctx: Context,
    doc_name: str,
    base_feature: str,
    chamfer_name: str,
    size: float,
    edge_refs: list[str] | None = None,
    body_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Add a chamfer to edges of an existing solid (PartDesign::Chamfer).

    Args:
        doc_name: Document containing the body and feature.
        base_feature: Name of the feature to chamfer.
        chamfer_name: Name for the resulting Chamfer feature.
        size: Chamfer size in mm (must be > 0).
        edge_refs: Optional list of edge references like ``["Edge1","Edge3"]``.
            If omitted, all edges are chamfered.
        body_name: Optional explicit PartDesign Body name.

    Returns:
        Success message and an isometric screenshot.
    """
    return chamfer_feature_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, base_feature, chamfer_name, size, edge_refs, body_name,
    )


@mcp.tool()
def boolean_union(
    ctx: Context,
    doc_name: str,
    shape1: str,
    shape2: str,
    result_name: str,
) -> list[TextContent | ImageContent]:
    """Compute the Boolean union (fuse) of two shapes (Part::Fuse).

    Args:
        doc_name: Document containing both shapes.
        shape1: Name of the first shape object.
        shape2: Name of the second shape object.
        result_name: Name for the resulting fused shape.

    Returns:
        Success message and an isometric screenshot.
    """
    return boolean_union_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, shape1, shape2, result_name,
    )


@mcp.tool()
def boolean_difference(
    ctx: Context,
    doc_name: str,
    shape1: str,
    shape2: str,
    result_name: str,
) -> list[TextContent | ImageContent]:
    """Subtract shape2 from shape1 (Part::Cut).

    Args:
        doc_name: Document containing both shapes.
        shape1: Name of the base shape.
        shape2: Name of the tool shape to subtract.
        result_name: Name for the resulting cut shape.

    Returns:
        Success message and an isometric screenshot.
    """
    return boolean_difference_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, shape1, shape2, result_name,
    )


@mcp.tool()
def boolean_intersection(
    ctx: Context,
    doc_name: str,
    shape1: str,
    shape2: str,
    result_name: str,
) -> list[TextContent | ImageContent]:
    """Compute the Boolean intersection (common) of two shapes (Part::Common).

    Args:
        doc_name: Document containing both shapes.
        shape1: Name of the first shape.
        shape2: Name of the second shape.
        result_name: Name for the resulting common shape.

    Returns:
        Success message and an isometric screenshot.
    """
    return boolean_intersection_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, shape1, shape2, result_name,
    )


# =============================================================================
# P4 — Gear library
# =============================================================================

@mcp.tool()
def create_involute_gear(
    ctx: Context,
    doc_name: str,
    gear_name: str,
    teeth: int,
    module: float,
    width: float,
    pressure_angle: float = 20.0,
    bore_diameter: float = 0.0,
    clearance: float = 0.0,
    backlash: float = 0.0,
    samples_per_flank: int = 12,
    body_name: str | None = None,
    sketch_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Create an involute spur gear using the correct mathematical involute profile.

    The tooth flanks follow the true involute of the base circle:
        x(t) = r_b*(cos(t) + t*sin(t))
        y(t) = r_b*(sin(t) - t*cos(t))

    This produces correct meshing geometry (replaces the deprecated
    ``create_spur_gear`` which used a smoothstep approximation).

    Args:
        doc_name: Document to create the gear in.
        gear_name: Name for the Pad feature.
        teeth: Number of teeth (minimum 3).
        module: Gear module in mm. Pitch diameter = module × teeth.
        width: Face width (pad length) in mm.
        pressure_angle: Pressure angle in degrees (default 20).
        bore_diameter: Optional centre bore diameter in mm.
        clearance: Extra root clearance in mm (added to standard 1.25m dedendum).
        backlash: Tooth backlash in mm at the pitch circle.
        samples_per_flank: Points per involute flank (higher = smoother, slower).
        body_name: Optional existing PartDesign Body.
        sketch_name: Optional sketch name (default: ``<gear_name>_Sketch``).

    Returns:
        Success message with gear metadata and an isometric screenshot.

    Examples:
        24-tooth module-2 gear with 6 mm bore:
        ```json
        {"doc_name":"GearDoc","gear_name":"Gear24","teeth":24,"module":2,"width":10,"bore_diameter":6}
        ```
    """
    return create_involute_gear_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, gear_name, teeth, module, width,
        pressure_angle, bore_diameter, clearance, backlash, samples_per_flank,
        body_name, sketch_name,
    )


@mcp.tool()
def create_helical_gear(
    ctx: Context,
    doc_name: str,
    gear_name: str,
    teeth: int,
    module: float,
    width: float,
    helix_angle: float = 15.0,
    pressure_angle: float = 20.0,
    bore_diameter: float = 0.0,
    clearance: float = 0.0,
    backlash: float = 0.0,
    samples_per_flank: int = 12,
    body_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Create a helical gear (involute profile + AdditiveHelix twist).

    Args:
        doc_name: Document to create the gear in.
        gear_name: Name for the feature.
        teeth: Number of teeth.
        module: Gear module in mm (normal module).
        width: Face width in mm.
        helix_angle: Helix angle in degrees (default 15).
        pressure_angle: Normal pressure angle in degrees (default 20).
        bore_diameter: Optional centre bore diameter in mm.
        clearance: Extra root clearance in mm.
        backlash: Tooth backlash in mm.
        samples_per_flank: Points per involute flank.
        body_name: Optional existing PartDesign Body.

    Returns:
        Success message with gear metadata and an isometric screenshot.
    """
    return create_helical_gear_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, gear_name, teeth, module, width,
        helix_angle, pressure_angle, bore_diameter, clearance, backlash,
        samples_per_flank, body_name,
    )


@mcp.tool()
def compute_gear_geometry(
    ctx: Context,
    teeth: int,
    module: float,
    pressure_angle: float = 20.0,
    clearance: float = 0.0,
    backlash: float = 0.0,
    helix_angle: float = 0.0,
) -> list[TextContent]:
    """Compute standard gear geometry parameters without creating geometry.

    Returns pitch diameter, base diameter, addendum, dedendum, circular pitch,
    and base pitch for the specified gear.

    Args:
        teeth: Number of teeth.
        module: Gear module in mm.
        pressure_angle: Pressure angle in degrees (default 20).
        clearance: Extra root clearance in mm.
        backlash: Tooth backlash in mm.
        helix_angle: Helix angle in degrees (0 = spur gear).

    Returns:
        JSON with all standard gear parameters.
    """
    return compute_gear_geometry_operation(
        get_freecad_connection(), state.only_text_feedback,
        teeth, module, pressure_angle, clearance, backlash, helix_angle,
    )


@mcp.tool()
def check_gear_pair(
    ctx: Context,
    teeth1: int,
    module1: float,
    teeth2: int,
    module2: float,
    pressure_angle: float = 20.0,
    center_distance: float | None = None,
) -> list[TextContent]:
    """Verify that two gears form a valid meshing pair.

    Checks module compatibility, computes gear ratio and theoretical centre
    distance. Optionally validates a specified centre distance.

    Args:
        teeth1: Teeth count of the first gear (driver).
        module1: Module of the first gear in mm.
        teeth2: Teeth count of the second gear (driven).
        module2: Module of the second gear in mm.
        pressure_angle: Shared pressure angle in degrees.
        center_distance: Optional measured centre distance to validate in mm.

    Returns:
        JSON with ``meshes`` (bool), ``gear_ratio``, ``theoretical_cd_mm``, and notes.
    """
    return check_gear_pair_operation(
        get_freecad_connection(), state.only_text_feedback,
        teeth1, module1, teeth2, module2, pressure_angle, center_distance,
    )


# =============================================================================
# P5 — Measurement & transforms
# =============================================================================

@mcp.tool()
def measure_distance(
    ctx: Context,
    doc_name: str,
    shape1_ref: str,
    shape2_ref: str,
) -> list[TextContent]:
    """Measure the minimum distance between two shapes.

    Args:
        doc_name: Document containing both shapes.
        shape1_ref: Name of the first shape object.
        shape2_ref: Name of the second shape object.

    Returns:
        JSON with ``distance`` in mm.
    """
    return measure_distance_operation(get_freecad_connection(), doc_name, shape1_ref, shape2_ref)


@mcp.tool()
def measure_angle(
    ctx: Context,
    doc_name: str,
    edge1_ref: str,
    edge2_ref: str,
) -> list[TextContent]:
    """Measure the angle between two edges or objects.

    Refs can be ``"ObjectName"`` or ``"ObjectName:EdgeN"`` (e.g. ``"Box:Edge1"``).

    Args:
        doc_name: Document containing the objects.
        edge1_ref: First edge reference.
        edge2_ref: Second edge reference.

    Returns:
        JSON with ``angle_deg`` in degrees.
    """
    return measure_angle_operation(get_freecad_connection(), doc_name, edge1_ref, edge2_ref)


@mcp.tool()
def measure_area(
    ctx: Context,
    doc_name: str,
    obj_name: str,
) -> list[TextContent]:
    """Measure the total surface area of a shape.

    Args:
        doc_name: Document containing the object.
        obj_name: Name of the shape object.

    Returns:
        JSON with ``area_mm2`` and ``area_cm2``.
    """
    return measure_area_operation(get_freecad_connection(), doc_name, obj_name)


@mcp.tool()
def measure_volume(
    ctx: Context,
    doc_name: str,
    obj_name: str,
) -> list[TextContent]:
    """Measure the volume of a solid shape.

    Args:
        doc_name: Document containing the object.
        obj_name: Name of the shape object.

    Returns:
        JSON with ``volume_mm3`` and ``volume_cm3``.
    """
    return measure_volume_operation(get_freecad_connection(), doc_name, obj_name)


@mcp.tool()
def bounding_box(
    ctx: Context,
    doc_name: str,
    obj_name: str,
) -> list[TextContent]:
    """Return the axis-aligned bounding box of a shape.

    Args:
        doc_name: Document containing the object.
        obj_name: Name of the shape object.

    Returns:
        JSON with xmin/ymin/zmin/xmax/ymax/zmax and dx/dy/dz dimensions.
    """
    return bounding_box_operation(get_freecad_connection(), doc_name, obj_name)


@mcp.tool()
def center_of_mass(
    ctx: Context,
    doc_name: str,
    obj_name: str,
) -> list[TextContent]:
    """Compute the centre of mass of a solid shape.

    Args:
        doc_name: Document containing the object.
        obj_name: Name of the shape object.

    Returns:
        JSON with ``x``, ``y``, ``z`` coordinates in mm.
    """
    return center_of_mass_operation(get_freecad_connection(), doc_name, obj_name)


@mcp.tool()
def validate_geometry(
    ctx: Context,
    doc_name: str,
    obj_name: str,
) -> list[TextContent]:
    """Validate the geometry of a shape and return diagnostic information.

    Checks whether the shape is null, valid, closed, and reports face/edge/vertex
    counts along with a BRep analysis result.

    Args:
        doc_name: Document containing the object.
        obj_name: Name of the shape object.

    Returns:
        JSON with validity flags, counts, volume/area, and BRep analysis output.
    """
    return validate_geometry_operation(get_freecad_connection(), doc_name, obj_name)


@mcp.tool()
def translate(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    dx: float,
    dy: float,
    dz: float,
) -> list[TextContent | ImageContent]:
    """Translate (move) an object by a displacement vector.

    Args:
        doc_name: Document containing the object.
        obj_name: Name of the object to translate.
        dx: X displacement in mm.
        dy: Y displacement in mm.
        dz: Z displacement in mm.

    Returns:
        Success message and a screenshot.
    """
    return translate_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, obj_name, dx, dy, dz,
    )


@mcp.tool()
def rotate(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    axis_x: float,
    axis_y: float,
    axis_z: float,
    angle_deg: float,
    center_x: float = 0.0,
    center_y: float = 0.0,
    center_z: float = 0.0,
) -> list[TextContent | ImageContent]:
    """Rotate an object around a specified axis.

    Args:
        doc_name: Document containing the object.
        obj_name: Name of the object to rotate.
        axis_x: X component of the rotation axis vector.
        axis_y: Y component of the rotation axis vector.
        axis_z: Z component of the rotation axis vector.
        angle_deg: Rotation angle in degrees (positive = CCW by right-hand rule).
        center_x: X coordinate of the rotation centre (default 0).
        center_y: Y coordinate of the rotation centre (default 0).
        center_z: Z coordinate of the rotation centre (default 0).

    Returns:
        Success message and a screenshot.
    """
    return rotate_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, obj_name, axis_x, axis_y, axis_z, angle_deg,
        center_x, center_y, center_z,
    )


@mcp.tool()
def scale(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    sx: float,
    sy: float,
    sz: float,
) -> list[TextContent | ImageContent]:
    """Scale an object non-uniformly along the three axes.

    Note: scaling a PartDesign solid converts it to a dumb Part::Feature.
    Use for Part workbench shapes or final geometry only.

    Args:
        doc_name: Document containing the object.
        obj_name: Name of the object to scale.
        sx: Scale factor along X.
        sy: Scale factor along Y.
        sz: Scale factor along Z.

    Returns:
        Success message and a screenshot.
    """
    return scale_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, obj_name, sx, sy, sz,
    )


# =============================================================================
# P6 — Import / export
# =============================================================================

@mcp.tool()
def export_step(
    ctx: Context,
    doc_name: str,
    file_path: str,
    obj_names: list[str] | None = None,
) -> list[TextContent]:
    """Export shapes to a STEP file.

    Args:
        doc_name: Document containing the shapes.
        file_path: Absolute path to the output STEP file.
        obj_names: Optional list of object names to export. If omitted,
            all objects with a Shape are exported.

    Returns:
        JSON with the count of exported objects and the file path.
    """
    return export_step_operation(get_freecad_connection(), doc_name, file_path, obj_names)


@mcp.tool()
def import_step(
    ctx: Context,
    doc_name: str,
    file_path: str,
) -> list[TextContent]:
    """Import a STEP file into an existing FreeCAD document.

    Args:
        doc_name: Target document name.
        file_path: Absolute path to the STEP file to import.

    Returns:
        JSON confirming success and the file path.
    """
    return import_step_operation(get_freecad_connection(), doc_name, file_path)


@mcp.tool()
def export_stl(
    ctx: Context,
    doc_name: str,
    file_path: str,
    obj_names: list[str] | None = None,
    mesh_deviation: float = 0.1,
) -> list[TextContent]:
    """Export shapes to an STL file (tessellated mesh).

    Args:
        doc_name: Document containing the shapes.
        file_path: Absolute path to the output STL file.
        obj_names: Optional list of object names. If omitted, all shapes exported.
        mesh_deviation: Tessellation accuracy in mm (smaller = finer, default 0.1).

    Returns:
        JSON with the count of exported objects, facet count, and file path.
    """
    return export_stl_operation(get_freecad_connection(), doc_name, file_path, obj_names, mesh_deviation)


@mcp.tool()
def export_brep(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    file_path: str,
) -> list[TextContent]:
    """Export a shape to a BREP file (OpenCASCADE native format).

    BREP preserves exact geometry and is lossless for round-tripping.

    Args:
        doc_name: Document containing the shape.
        obj_name: Name of the shape object to export.
        file_path: Absolute path to the output BREP file.

    Returns:
        JSON confirming success and the file path.
    """
    return export_brep_operation(get_freecad_connection(), doc_name, obj_name, file_path)


@mcp.tool()
def import_brep(
    ctx: Context,
    doc_name: str,
    file_path: str,
    obj_name: str = "BRepImport",
) -> list[TextContent]:
    """Import a BREP file into an existing FreeCAD document.

    Args:
        doc_name: Target document name.
        file_path: Absolute path to the BREP file to import.
        obj_name: Name for the imported Part::Feature object.

    Returns:
        JSON confirming success and the object name.
    """
    return import_brep_operation(get_freecad_connection(), doc_name, file_path, obj_name)


@mcp.tool()
def set_color(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    r: float,
    g: float,
    b: float,
    transparency: float = 0.0,
) -> list[TextContent | ImageContent]:
    """Set the display colour and transparency of an object.

    Args:
        doc_name: Document containing the object.
        obj_name: Name of the object.
        r: Red channel 0.0–1.0.
        g: Green channel 0.0–1.0.
        b: Blue channel 0.0–1.0.
        transparency: Transparency 0.0 (opaque) – 1.0 (fully transparent).

    Returns:
        Success message and a screenshot.
    """
    return set_color_operation(
        get_freecad_connection(), state.only_text_feedback,
        doc_name, obj_name, r, g, b, transparency,
    )


# =============================================================================
# P7 — Assembly references, sketch geometry, path wires
# =============================================================================

@mcp.tool()
def get_document_tree(
    ctx: Context,
    doc_name: str,
    root_filter: str | None = None,
    max_depth: int = 4,
    include: list[str] | None = None,
    include_properties: list[str] | None = None,
    selected_nodes: list[str] | None = None,
) -> list[TextContent]:
    """Return a compact document/container tree.

    Args:
        doc_name: Document to inspect.
        root_filter: Optional Name/Label substring used to select tree roots.
        max_depth: Maximum container depth to include.
        include: Fields to include, defaulting to Name/Label/TypeId/Visibility/State.
        include_properties: Optional object properties to include.
        selected_nodes: Names/labels whose properties should be included.

    Returns:
        JSON tree for compact agent inspection.
    """
    return get_document_tree_operation(
        get_freecad_connection(),
        doc_name,
        root_filter,
        max_depth,
        include,
        include_properties,
        selected_nodes,
    )


@mcp.tool()
def create_part_container(
    ctx: Context,
    doc_name: str,
    part_name: str,
    parent_container: str | None = None,
    if_exists: Literal["error", "skip", "replace"] = "error",
) -> list[TextContent | ImageContent]:
    """Create an App::Part assembly container."""
    return create_part_container_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        part_name,
        parent_container,
        if_exists,
    )


@mcp.tool()
def move_object(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    target_container: str,
    remove_from_old_parent: bool = True,
) -> list[TextContent | ImageContent]:
    """Move an object into a PartDesign Body or App::Part container."""
    return move_object_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_name,
        target_container,
        remove_from_old_parent,
    )


@mcp.tool()
def create_subshape_binder(
    ctx: Context,
    doc_name: str,
    binder_name: str,
    source_object: str,
    sub_elements: list[str] | None = None,
    target_body: str | None = None,
    target_container: str | None = None,
    relative: bool = False,
    sync_placement: bool = True,
    if_exists: Literal["error", "skip", "replace"] = "error",
) -> list[TextContent | ImageContent]:
    """Create a PartDesign SubShapeBinder with placement validation."""
    return create_subshape_binder_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        binder_name,
        source_object,
        sub_elements,
        target_body,
        target_container,
        relative,
        sync_placement,
        if_exists,
    )


@mcp.tool()
def create_datum_plane(
    ctx: Context,
    doc_name: str,
    plane_name: str,
    body_name: str,
    mode: Literal[
        "midpoint_between_faces",
        "through_point",
        "offset_from_face",
        "between_parallel_planes",
        "plane_from_binder_face",
    ],
    source_ref: str | None = None,
    face_a: str | None = None,
    face_b: str | None = None,
    offset_along_normal: list[float] | None = None,
    map_mode: str = "FlatFace",
    if_exists: Literal["error", "skip", "replace"] = "error",
) -> list[TextContent | ImageContent]:
    """Create a PartDesign datum plane for assembly reference workflows."""
    return create_datum_plane_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        plane_name,
        body_name,
        mode,
        source_ref,
        face_a,
        face_b,
        offset_along_normal,
        map_mode,
        if_exists,
    )


@mcp.tool()
def get_sketch_geometry(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    include_constraints: bool = True,
    include_external: bool = True,
    global_coords: bool = True,
) -> list[TextContent]:
    """Return sketch geometry endpoints, construction flags, constraints, and external refs."""
    return get_sketch_geometry_operation(
        get_freecad_connection(),
        doc_name,
        sketch_name,
        include_constraints,
        include_external,
        global_coords,
    )


@mcp.tool()
def sketch_add_external_projection(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    source_ref: str,
    projection_mode: Literal["auto", "edge", "face", "point"] = "auto",
    defining: bool = False,
) -> list[TextContent | ImageContent]:
    """Add external geometry to a sketch with assembly-aware preflight checks."""
    return sketch_add_external_projection_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        sketch_name,
        source_ref,
        projection_mode,
        defining,
    )


@mcp.tool()
def build_path_wire(
    ctx: Context,
    doc_name: str,
    wire_name: str,
    segments: list[dict[str, Any]],
    tolerance_mm: float = 0.5,
    container: str | None = None,
    if_exists: Literal["error", "skip", "replace"] = "error",
) -> list[TextContent | ImageContent]:
    """Build a Part wire from sketch geometry and optional bridge segments."""
    return build_path_wire_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        wire_name,
        segments,
        tolerance_mm,
        container,
        if_exists,
    )


@mcp.tool()
def sweep_pipe(
    ctx: Context,
    doc_name: str,
    path_wire: str,
    diameter_mm: float,
    solid_name: str,
    profile_mode: str = "frenet",
    color: list[float] | None = None,
    container: str | None = None,
    if_exists: Literal["error", "skip", "replace"] = "error",
) -> list[TextContent | ImageContent]:
    """Sweep a circular solid pipe along a wire path."""
    return sweep_pipe_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        path_wire,
        diameter_mm,
        solid_name,
        profile_mode,
        color,
        container,
        if_exists,
    )


@mcp.prompt()
def asset_creation_strategy() -> str:
    return ASSET_CREATION_STRATEGY


def _validate_host(value: str) -> str:
    """Validate that *value* is a valid IP address or hostname.

    Used as the ``type`` callback for the ``--host`` argparse argument.
    Raises ``argparse.ArgumentTypeError`` on invalid input.
    """
    import argparse

    import validators

    if validators.ipv4(value) or validators.ipv6(value) or validators.hostname(value):
        return value
    raise argparse.ArgumentTypeError(
        f"Invalid host: '{value}'. Must be a valid IP address or hostname."
    )


def main():
    """Run the MCP server"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--only-text-feedback", action="store_true", help="Only return text feedback")
    parser.add_argument("--host", type=_validate_host, default="localhost", help="Host address of the FreeCAD RPC server to connect to (default: localhost)")
    args = parser.parse_args()
    state.only_text_feedback = args.only_text_feedback
    state.rpc_host = args.host
    logger.info(f"Only text feedback: {state.only_text_feedback}")
    logger.info(f"Connecting to FreeCAD RPC server at: {state.rpc_host}")
    mcp.run()
