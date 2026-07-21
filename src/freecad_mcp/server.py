import logging
import json
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent

from .freecad_client import FreeCADConnection
from .responses import json_response, tool_fail
from .operations import (
    # Core
    close_document_operation,
    create_document_operation,
    create_object_operation,
    delete_object_operation,
    edit_object_operation,
    execute_code_async_operation,
    execute_code_operation,
    get_object_operation,
    get_objects_operation,
    inspect_references_operation,
    get_parts_list_operation,
    get_recompute_log_operation,
    get_sketch_diagnostics_operation,
    get_view_operation,
    save_view_sequence_operation,
    encode_view_video_operation,
    animate_placement_operation,
    refresh_view_operation,
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
    repair_references_operation,
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
    get_global_shape_operation,
    common_volume_along_path_operation,
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
    create_assembly_grounded_joint_operation,
    create_assembly_joint_operation,
    create_assembly_operation,
    create_datum_plane_operation,
    create_part_container_operation,
    create_subshape_binder_operation,
    get_document_tree_operation,
    get_sketch_geometry_operation,
    move_object_operation,
    sketch_add_external_projection_operation,
    solve_assembly_operation,
    sweep_pipe_operation,
    # Diagnostics — read-only P1/P8/P10 guards
    capture_state_operation,
    edge_axis_operation,
    face_normal_operation,
    find_edges_operation,
    find_faces_operation,
    geometric_diff_operation,
    placement_audit_operation,
    preview_attachment_operation,
    relink_references_operation,
    create_placement_binder_operation,
    create_placement_datum_operation,
    run_transaction_operation,
    validate_movement_follow_operation,
    audit_hardcoded_dimensions_operation,
    inspect_geometry_operation,
    get_dependency_graph_operation,
    match_subshape_operation,
    # Interactive GUI
    open_document_operation,
    activate_document_operation,
    set_tree_expanded_operation,
    select_subshapes_operation,
    get_selection_operation,
    get_gui_state_operation,
    recompute_and_wait_operation,
    set_section_view_operation,
    diagnose_pocket_operation,
    diagnose_helix_operation,
    compare_documents_operation,
    # Snapshot — I7 in-process document copies (P12)
    restore_operation,
    snapshot_operation,
    reload_document_operation,
    run_fem_analysis_operation,
    # Parametric — Spreadsheet / expressions / Body / named constraints
    spreadsheet_create_operation,
    spreadsheet_set_cells_operation,
    spreadsheet_get_cells_operation,
    spreadsheet_set_alias_operation,
    spreadsheet_list_aliases_operation,
    set_expression_operation,
    clear_expression_operation,
    list_expressions_operation,
    body_create_operation,
    body_set_tip_operation,
    sketch_attach_operation,
    sketch_edit_constraint_operation,
    diagnose_parametric_operation,
)
from .prompt_text import ASSET_CREATION_STRATEGY
from .server_state import ServerState


logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("FreeCADMCPserver")
logger.setLevel(logging.INFO)

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
        conn = FreeCADConnection(
            host=state.rpc_host,
            port=state.rpc_port,
            expected_instance_id=state.instance_id,
        )
        if not conn.ping():
            logger.error("Failed to ping FreeCAD")
            raise Exception(
                "Failed to connect to FreeCAD. Make sure the FreeCAD addon is running."
            )
        # When an instance id was configured, refuse to proceed unless the addon
        # on this port reports the same identity (isolated-instance safety).
        if state.instance_id:
            conn.verify_instance()
        state.freecad_connection = conn
    return state.freecad_connection


@mcp.tool()
def check_rpc_sync(ctx: Context) -> CallToolResult:
    """Verify that the next FreeCAD GUI response belongs to this exact call.

    A unique nonce is round-tripped through FreeCAD's GUI task queue. Use this
    after an execute timeout or before relying on model inspection results. A
    timeout or nonce mismatch means the queue is not safe for further work.
    """
    nonce = uuid.uuid4().hex
    result = get_freecad_connection().check_rpc_sync(nonce)
    if result.get("success") and result.get("nonce") == nonce:
        return json_response({"ok": True, "synchronized": True, "nonce": nonce})
    details = {
        "ok": False,
        "synchronized": False,
        "expected_nonce": nonce,
        "rpc_result": result,
    }
    return tool_fail(
        "FreeCAD GUI-RPC synchronization check failed.\n"
        + json.dumps(details, ensure_ascii=False, indent=2, default=str),
        structured=details,
    )


@mcp.tool()
def create_document(ctx: Context, name: str) -> CallToolResult:
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
) -> CallToolResult:
    """Create a new object in FreeCAD.
    Object type is starts with "Part::" or "Draft::" or "PartDesign::" or "Fem::".

    NOTE: For mechanical parts the default workflow is a parametric PartDesign feature
    history (body_create -> sketch_create/sketch_attach -> constraints ->
    get_sketch_diagnostics -> pad_feature/pocket_feature), not generic primitives. Use
    this tool for reference/non-parametric geometry, imported assets, temporary validation
    solids, or when a specific primitive is explicitly requested. See the
    asset_creation_strategy prompt.

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
        The `Shape` property is required (legacy `Part` is also accepted).
        On FreeCAD 1.x the size limits are `CharacteristicLengthMax/Min`;
        the legacy `ElementSizeMax/Min` keys are also accepted.
        ```json
        {
            "doc_name": "MyFEMMesh",
            "obj_name": "FemMesh",
            "obj_type": "Fem::FemMeshGmsh",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "Shape": "MyObject",
                "CharacteristicLengthMax": 10,
                "CharacteristicLengthMin": 0.1
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
) -> CallToolResult:
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
def inspect_references(
    ctx: Context,
    doc_name: str,
    object_names: list[str] | None = None,
    only_invalid: bool = False,
    validate: bool = False,
) -> CallToolResult:
    """Inspect link/subelement properties without evaluating their owner shapes.

    This is the recovery-safe alternative to ``get_object`` for a document that
    contains stale ``EdgeNNN``, ``FaceNNN``, or ``VertexNNN`` references. It
    scans link properties such as ``Support``, ``AttachmentSupport``, and a
    sketch's ordered ``ExternalGeometry`` list. It never recomputes the document.

    Args:
        doc_name: Open FreeCAD document name.
        object_names: Optional owner objects to inspect; omit to scan the document.
        only_invalid: Return only properties containing invalid subelements.
        validate: Resolve referenced subelements on their target shapes. Leave
            false for circularly broken documents; validity is then reported as
            unevaluated instead of reading ``Shape``.

    Returns:
        Structured link properties, preserving target and subelement order.
    """
    return inspect_references_operation(
        get_freecad_connection(),
        doc_name,
        object_names,
        only_invalid=only_invalid,
        validate=validate,
    )


@mcp.tool()
def repair_references(
    ctx: Context,
    doc_name: str,
    repairs: list[dict[str, Any]],
    recompute: bool = False,
    validate: bool = False,
) -> CallToolResult:
    """Atomically replace broken link/subelement properties without recomputing.

    Use this when stale external geometry prevents normal MCP write/evaluate
    calls. Each repair replaces one complete link property. Keeping the same
    reference-list order preserves Sketcher external-geometry indices.

    Example ``repairs`` value::

        [{
          "object": "ServoEdgeBinder",
          "property": "Support",
          "references": [{
            "document": "Model",
            "object": "ServoBody",
            "subelements": ["Edge42"]
          }]
        }]

    Batch every known broken property into one call. The batch is preflighted
    and applied in a FreeCAD transaction. Recompute defaults to false so all
    circularly broken links can be repaired before dependent geometry evaluates.
    This tool does not save the document.

    Args:
        doc_name: Open FreeCAD document containing the owner objects.
        repairs: Complete replacement references for each owner property.
        recompute: Recompute once after committing the entire batch.
        validate: Confirm proposed subelements exist before writing. This reads
            target shapes, so leave false for the circular-recovery path and
            validate with an explicit recompute after the complete batch.

    Returns:
        Applied properties, commit state, deferred/attempted recompute state,
        and any invalid links remaining on the repaired owner objects.
    """
    return repair_references_operation(
        get_freecad_connection(),
        doc_name,
        repairs,
        recompute=recompute,
        validate=validate,
    )


@mcp.tool()
def delete_object(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    recursive: bool = False,
    force: bool = False,
) -> CallToolResult:
    """Delete an object without silently orphaning its dependents (I5 / P6).

    FreeCAD's delete deliberately does not remove an object's dependents, leaving
    them Invalid. To avoid silent orphans this tool:
      * ``recursive=True`` -> remove dependents (leaves first) then the object;
      * ``force=True``      -> remove only the object and report the orphans left;
      * otherwise           -> refuse and list the dependents so the agent decides.

    Args:
        doc_name: The name of the document to delete the object from.
        obj_name: The name of the object to delete.
        recursive: If True, delete the object's dependents first (no orphans).
        force: If True, delete only the object even if it has dependents (orphans
            remain and are reported).

    Returns:
        JSON ``{ok, object, deleted, refused, dependents|orphans_left, ...}``
        plus a recompute log of any non-clean objects, and a screenshot.
    """
    return delete_object_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_name,
        recursive=recursive,
        force=force,
    )


@mcp.tool()
def execute_code_async(ctx: Context, code: str) -> list[TextContent]:
    """Execute Python code in FreeCAD without waiting for completion.

    Use this ONLY for long-running background computations that do NOT touch the
    FreeCAD GUI or mutate the FreeCAD document tree directly.

    This tool runs the submitted code in a background thread and returns
    immediately. Because it does not run on FreeCAD's main GUI thread, the code
    must NOT call FreeCADGui APIs, manipulate the active view or selection, create
    or edit document objects, change object properties, call doc.recompute(), or
    save documents.

    For code that touches FreeCAD documents, document objects, FreeCADGui, the
    active view, selection, recompute, or save operations, use execute_code instead.
    execute_code runs on the FreeCAD GUI thread and is the safe default for normal
    FreeCAD automation.

    Use execute_code_async only for background-safe work such as long-running
    pure OCCT geometry calculations (e.g. fuse/cut/loft on already-fetched shapes)
    or other CPU-bound computations that do not interact with the document or GUI.

    Typical usage pattern:
    1. Fetch shapes into local variables first (via execute_code on the GUI thread).
    2. Store intermediate results in a module-level Python variable (not in the
       FreeCAD document) so execute_code can read them later.
    3. Run the heavy computation via execute_code_async.
    4. After the expected computation time has elapsed, apply results to the
       document via execute_code (which runs on the GUI thread).

    Args:
        code: Background-safe Python code to execute.

    Returns:
        A message confirming that background execution has started.
    """
    return execute_code_async_operation(get_freecad_connection(), code)


@mcp.tool()
def execute_code(
    ctx: Context,
    code: str,
    document: str | None = None,
    recompute: str = "none",
    recompute_documents: list[str] | None = None,
    read_only: bool = False,
    restore_active_document: bool = True,
    activate_document: bool = False,
    capture_view: bool = False,
    execution_mode: Literal["gui", "worker", "auto"] = "auto",
    timeout_seconds: float | None = None,
    link_policy: Literal["strict", "warn"] = "strict",
) -> CallToolResult:
    """Execute arbitrary Python code in FreeCAD.

    Args:
        code: The Python code to execute.
        document: Target document name for scoped recompute/error reporting.
        recompute: ``none`` (default for inspection), ``target``, or ``all``.
        recompute_documents: Explicit document list to recompute when recompute is ``target``.
        read_only: When true, blocks ``save``/``saveAs`` on open documents.
        restore_active_document: Restore the active document after execution.
        activate_document: Activate ``document`` before running code.
        capture_view: Include a viewport screenshot (default false).
        execution_mode: Conservative ``auto`` (default), explicit ``gui``, or isolated ``worker``.
        timeout_seconds: Hard worker timeout from 1 to 900 seconds.
        link_policy: Worker snapshot policy for broken joint/link refs. ``strict``
            fails the snapshot; ``warn`` continues and returns ``link_warnings``.
            Only meaningful with ``execution_mode="worker"``.

    Returns:
        Execution output with structured session/recompute metadata, or an error with traceback.
    """
    return execute_code_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        code,
        document=document,
        recompute=recompute,
        recompute_documents=recompute_documents,
        read_only=read_only,
        restore_active_document=restore_active_document,
        activate_document=activate_document,
        capture_view=capture_view,
        execution_mode=execution_mode,
        timeout_seconds=timeout_seconds,
        link_policy=link_policy,
    )


@mcp.tool()
def get_worker_status(ctx: Context) -> CallToolResult:
    """Report isolated FreeCADCmd availability and whether a worker job is active.

    Returns JSON with:
    - ``state``: ``idle`` | ``busy`` | ``unavailable``
    - ``busy``: true while a FreeCADCmd job is running
    - ``active_job_id`` / ``pending_job_ids`` / ``queue_depth``
    - ``available``, ``version``, ``executable``, ``last_error``
    """
    try:
        return json_response(get_freecad_connection().get_worker_status())
    except Exception as exc:
        return tool_fail(f"Failed to get worker status: {exc}")


@mcp.tool()
def cancel_worker_job(ctx: Context, job_id: str) -> CallToolResult:
    """Cancel a pending worker job or terminate the active worker process tree."""
    try:
        return json_response(get_freecad_connection().cancel_worker_job(job_id))
    except Exception as exc:
        return tool_fail(f"Failed to cancel worker job: {exc}")


@mcp.tool()
def get_view(
    ctx: Context,
    view_name: Literal["Isometric", "Front", "Top", "Right", "Back", "Left", "Bottom", "Dimetric", "Trimetric", "Rear", "Side", "SideRight", "SideLeft"],
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
    focus_objects: list[str] | None = None,
    yaw_deg: float | None = None,
) -> CallToolResult:
    """Get a screenshot of the active view.

    Args:
        view_name: Standard view preset. Aliases: Rear→Back, Side/SideRight→Right, SideLeft→Left.
        Available: Isometric, Front, Top, Right, Back, Left, Bottom, Dimetric, Trimetric
        (plus Rear, Side, SideRight, SideLeft aliases).
        width: The width of the screenshot in pixels. If not specified, uses the viewport width.
        height: The height of the screenshot in pixels. If not specified, uses the viewport height.
        focus_object: Optional single object name to frame. Comma-separated names are also accepted.
        focus_objects: Optional list of object names to frame together (preferred for stations/assemblies).
        yaw_deg: Optional extra camera yaw in degrees after framing.

    Returns:
        A screenshot of the active view.
    """
    return get_view_operation(
        get_freecad_connection(),
        view_name,
        width,
        height,
        focus_object=focus_object,
        focus_objects=focus_objects,
        yaw_deg=yaw_deg,
    )


@mcp.tool()
def save_view_sequence(
    ctx: Context,
    frames: list[dict[str, Any]] | None = None,
    width: int | None = None,
    height: int | None = None,
    orbit: dict[str, Any] | None = None,
) -> CallToolResult:
    """Capture multiple framed screenshots for motion/station review.

    Provide ``frames`` and/or ``orbit``.

    Frame dict fields:
    - ``view_name`` (default ``Isometric``)
    - ``focus_object`` / ``focus_objects``
    - ``yaw_deg``
    - ``label``

    Orbit dict fields:
    - ``focus_object`` / ``focus_objects``
    - ``steps`` (default 8)
    - ``view_name`` (default ``Isometric``)
    - ``yaw_start_deg`` (default 0)

    Returns text metadata plus one PNG image per successful frame.
    """
    return save_view_sequence_operation(
        get_freecad_connection(),
        frames=frames,
        width=width,
        height=height,
        orbit=orbit,
        only_text_feedback=state.only_text_feedback,
    )


@mcp.tool()
def encode_view_video(
    ctx: Context,
    frames: list[dict[str, Any]] | None = None,
    orbit: dict[str, Any] | None = None,
    frame_paths: list[str] | None = None,
    output_path: str | None = None,
    fps: float = 8.0,
    width: int | None = None,
    height: int | None = None,
) -> CallToolResult:
    """Encode a view sequence to MP4 using system ffmpeg (not a git submodule).

    Provide existing ``frame_paths`` and/or capture via ``frames``/``orbit``
    (same shape as ``save_view_sequence``). Resolves ffmpeg from
    ``FREECAD_MCP_FFMPEG`` or PATH.
    """
    return encode_view_video_operation(
        get_freecad_connection(),
        frames=frames,
        orbit=orbit,
        frame_paths=frame_paths,
        output_path=output_path,
        fps=fps,
        width=width,
        height=height,
        only_text_feedback=state.only_text_feedback,
    )


@mcp.tool()
def refresh_view(
    ctx: Context,
    focus_objects: list[str] | None = None,
    focus_object: str | None = None,
    touch_objects: list[str] | None = None,
    fit: bool = False,
    capture: bool = False,
    view_name: Literal["Isometric", "Front", "Top", "Right", "Back", "Left", "Bottom", "Dimetric", "Trimetric"] = "Isometric",
) -> CallToolResult:
    """Force a GUI redraw after Link/shape edits; optionally touch Placement and frame."""
    return refresh_view_operation(
        get_freecad_connection(),
        focus_objects=focus_objects,
        focus_object=focus_object,
        touch_objects=touch_objects,
        fit=fit,
        capture=capture,
        view_name=view_name,
        only_text_feedback=state.only_text_feedback,
    )


@mcp.tool()
def animate_placement(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    keyframes: list[dict[str, Any]] | None = None,
    path_object: str | None = None,
    sample_count: int = 12,
    view_name: Literal["Isometric", "Front", "Top", "Right", "Back", "Left", "Bottom", "Dimetric", "Trimetric"] = "Isometric",
    focus_objects: list[str] | None = None,
    width: int | None = None,
    height: int | None = None,
    encode_video: bool = False,
    fps: float = 8.0,
    output_path: str | None = None,
) -> CallToolResult:
    """Animate an object's Placement along keyframes or a path wire, capture frames, restore.

    Prefer this over Shape edits for App::Link visibility. Optionally encodes MP4
    via system ffmpeg when ``encode_video=True``.
    """
    return animate_placement_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_name,
        keyframes=keyframes,
        path_object=path_object,
        sample_count=sample_count,
        view_name=view_name,
        focus_objects=focus_objects,
        width=width,
        height=height,
        encode_video=encode_video,
        fps=fps,
        output_path=output_path,
    )


@mcp.tool()
def insert_part_from_library(ctx: Context, relative_path: str) -> CallToolResult:
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
def get_objects(ctx: Context, doc_name: str) -> CallToolResult:
    """Get all objects in a document.
    You can use this tool to get the objects in a document to see what you can check or edit.

    Args:
        doc_name: The name of the document to get the objects from.

    Returns:
        A list of objects in the document and a screenshot of the document.
    """
    return get_objects_operation(get_freecad_connection(), state.only_text_feedback, doc_name)


@mcp.tool()
def get_object(ctx: Context, doc_name: str, obj_name: str) -> CallToolResult:
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
def get_parts_list(ctx: Context) -> CallToolResult:
    """Get the list of parts in the parts library addon.
    """
    return get_parts_list_operation(get_freecad_connection())


@mcp.tool()
def reload_document(ctx: Context, doc_name: str) -> list[TextContent]:
    """Close and re-open a document to pick up external file changes.

    Use this AFTER the document's .FCStd file has been modified by
    something outside of FreeCAD's GUI process — for example, a
    headless `freecadcmd` script that edited and saved the file. The
    open GUI document is otherwise unaware of on-disk changes; this
    tool closes the stale in-memory copy and reopens the file from
    disk so the GUI shows current geometry.

    Args:
        doc_name: The name of the open document to reload. Must match
            the name shown by ``list_documents``.

    Returns:
        A message confirming the document was reloaded, or describing
        the failure (document not loaded, no associated file, etc).

    Examples:
        ```json
        {
            "doc_name": "chassis"
        }
        ```
    """
    return reload_document_operation(get_freecad_connection(), doc_name)


@mcp.tool()
def list_documents(ctx: Context) -> CallToolResult:
    """Get the list of open documents in FreeCAD.

    Returns:
        A list of document names.
    """
    return list_documents_operation(get_freecad_connection())


@mcp.tool()
def open_document(ctx: Context, path: str) -> CallToolResult:
    """Open a ``.FCStd`` (or other FreeCAD-supported) file in the running GUI.

    Use this to load V7 and V8 into the same FreeCAD session for comparison.
    """
    return open_document_operation(get_freecad_connection(), path)


@mcp.tool()
def activate_document(ctx: Context, doc_name: str) -> CallToolResult:
    """Make an already-open document the active GUI document."""
    return activate_document_operation(get_freecad_connection(), doc_name)


@mcp.tool()
def set_tree_expanded(
    ctx: Context,
    doc_name: str,
    object_names: list[str] | None = None,
    mode: Literal["expand", "collapse", "expand_document", "collapse_document"] = "expand",
) -> CallToolResult:
    """Expand or collapse model-tree items in the FreeCAD GUI.

    Selects ``object_names`` then runs Std_TreeExpand / Std_TreeCollapse.
    Modes ``expand_document`` / ``collapse_document`` operate on the whole tree.
    """
    return set_tree_expanded_operation(
        get_freecad_connection(), doc_name, object_names, mode
    )


@mcp.tool()
def select_subshapes(
    ctx: Context,
    doc_name: str,
    selections: list[Any],
    clear: bool = True,
) -> CallToolResult:
    """Select GUI-visible objects or sub-shapes (FaceN/EdgeN/VertexN).

    Each selection may be ``\"Box\"``, ``\"Box:Face1\"``, or
    ``{\"object\": \"Box\", \"sub\": \"Face1\"}``. Prefer ``find_faces`` to
    discover indices, then this tool to highlight them in the GUI.
    """
    return select_subshapes_operation(
        get_freecad_connection(), doc_name, selections, clear
    )


@mcp.tool()
def get_selection(ctx: Context) -> CallToolResult:
    """Return the current FreeCADGui selection (document/object/sub)."""
    return get_selection_operation(get_freecad_connection())


@mcp.tool()
def get_gui_state(ctx: Context) -> CallToolResult:
    """Report the active GUI context (read-only).

    Returns JSON with the active document, active PartDesign Body, active
    workbench, the object currently in edit-mode, and the current selection.
    Use it to orient before editing -- e.g. confirm the right Body is active
    before adding a sketch/feature, or check whether a Sketch is open for edit.
    """
    return get_gui_state_operation(get_freecad_connection())


@mcp.tool()
def recompute_and_wait(ctx: Context, doc_name: str) -> CallToolResult:
    """Recompute a document and block until the GUI is idle, then report state.

    An explicit recompute-complete + GUI-idle barrier: runs the recompute on the
    GUI thread, drains queued Qt events, and returns per-object recompute state
    (errors, still-Touched objects, whether the document settled). Run it after a
    batch of edits, or after an execute_code that may have left async work, before
    trusting follow-up model checks. Complements ``check_rpc_sync`` (which only
    proves the RPC queue is live, not that a recompute finished).
    """
    return recompute_and_wait_operation(get_freecad_connection(), doc_name)


@mcp.tool()
def set_section_view(
    ctx: Context,
    enabled: bool | None = None,
    base: list[float] | None = None,
    normal: list[float] | None = None,
    placement: dict[str, Any] | None = None,
    no_manip: bool = True,
) -> CallToolResult:
    """Enable, disable, or query the active view clipping (section) plane.

    Pass ``enabled=True/False`` to toggle. Optionally set plane ``base`` +
    ``normal`` (or a full ``placement`` dict). Omit args to query status.
    """
    return set_section_view_operation(
        get_freecad_connection(),
        enabled=enabled,
        placement=placement,
        base=base,
        normal=normal,
        no_manip=no_manip,
    )


@mcp.tool()
def diagnose_pocket(
    ctx: Context,
    doc_name: str,
    pocket_name: str,
) -> CallToolResult:
    """Diagnose a PartDesign Pocket: support/profile, direction, reversed, length, geometry."""
    return diagnose_pocket_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        pocket_name,
    )


@mcp.tool()
def diagnose_helix(
    ctx: Context,
    doc_name: str,
    helix_name: str,
) -> CallToolResult:
    """Diagnose a helix/helical-sweep: axis, placement, profile, handedness, pitch/height, result."""
    return diagnose_helix_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        helix_name,
    )


@mcp.tool()
def compare_documents(
    ctx: Context,
    doc_a: str,
    doc_b: str,
    object_pairs: list[Any] | None = None,
) -> CallToolResult:
    """Compare two open documents (e.g. V7 vs V8) via paired geometric state diffs.

    ``object_pairs`` optional list of ``{\"a\": \"Body\", \"b\": \"Body\"}`` or
    ``[\"BodyV7\", \"BodyV8\"]``. When omitted, compares all objects by name.
    """
    return compare_documents_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_a,
        doc_b,
        object_pairs=object_pairs,
    )


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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo1, pos1, geo2, pos2,
    )


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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo,
    )


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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo, value, pos, name,
    )


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
        get_freecad_connection(), state.only_text_feedback,
        doc_name, sketch_name, geo, value, name,
    )


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
    strict: bool = False,
) -> CallToolResult:
    """Extrude (pad) a closed sketch profile into a 3-D solid (PartDesign::Pad).

    Strict PartDesign: the Pad is always created inside a PartDesign Body. If
    `body_name` is given it must resolve; otherwise the Body that owns the sketch
    is auto-detected. If no owning Body can be found the tool FAILS -- it never
    falls back to a loose, non-parametric feature in the document. Before building,
    the sketch is checked for conflicting/malformed constraints and a closed
    profile; after building, Body membership, Body.Tip, and a non-null solid are
    verified. The whole build is wrapped in a transaction, so a failed check leaves
    no partial feature behind.

    Args:
        doc_name: The document containing the sketch and body.
        sketch_name: Name of the sketch to extrude.
        pad_name: Name for the resulting Pad feature.
        length: Extrusion distance in mm.
        body_name: Optional explicit PartDesign Body name.
        symmetric: If true, extrude equally in both directions (length/2 each).
        reversed_dir: If true, reverse the extrusion direction.
        strict: If true, require an explicit `body_name` (owning-Body auto-detect
            is disabled). Recommended for a deterministic PartDesign history.

    Returns:
        A structured JSON workflow result (document, body, sketch, feature,
        attachment, tip, solid_count, state, bbox, diagnostics) plus an isometric
        screenshot, or a clear failure.

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
        strict,
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
    strict: bool = False,
) -> CallToolResult:
    """Cut (pocket) a closed sketch profile into an existing solid (PartDesign::Pocket).

    Strict PartDesign: the Pocket is always created inside a PartDesign Body. If
    `body_name` is given it must resolve; otherwise the Body that owns the sketch
    is auto-detected. If no owning Body can be found the tool FAILS -- it never
    falls back to a loose feature in the document. Before building, the sketch is
    checked for conflicting/malformed constraints and a closed profile; after
    building, Body membership, Body.Tip, and a non-null solid are verified. The
    whole build is wrapped in a transaction, so a failed check leaves no partial
    feature behind.

    Args:
        doc_name: The document containing the sketch and body.
        sketch_name: Name of the sketch to use as the cut profile.
        pocket_name: Name for the resulting Pocket feature.
        length: Cut depth in mm.
        body_name: Optional explicit PartDesign Body name.
        symmetric: If true, cut equally in both directions.
        reversed_dir: If true, reverse the cut direction.
        strict: If true, require an explicit `body_name` (owning-Body auto-detect
            is disabled). Recommended for a deterministic PartDesign history.

    Returns:
        A structured JSON workflow result (document, body, sketch, feature,
        attachment, tip, solid_count, state, bbox, diagnostics) plus an isometric
        screenshot, or a clear failure.

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
        strict,
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
def recompute_document(ctx: Context, doc_name: str) -> CallToolResult:
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
def undo(ctx: Context, doc_name: str) -> CallToolResult:
    """Undo the last operation in a FreeCAD document.

    Args:
        doc_name: The document to undo in.

    Returns:
        A message indicating success or failure.
    """
    return undo_operation(get_freecad_connection(), doc_name)


@mcp.tool()
def redo(ctx: Context, doc_name: str) -> CallToolResult:
    """Redo the previously undone operation in a FreeCAD document.

    Args:
        doc_name: The document to redo in.

    Returns:
        A message indicating success or failure.
    """
    return redo_operation(get_freecad_connection(), doc_name)


@mcp.tool()
def get_recompute_log(ctx: Context, doc_name: str) -> CallToolResult:
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
        get_freecad_connection(), state.only_text_feedback, doc_name, sheet_name
    )


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
        get_freecad_connection(), state.only_text_feedback, doc_name, sheet_name, cells
    )


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
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        sheet_name,
        addresses,
    )


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
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        sheet_name,
        address,
        alias,
    )


@mcp.tool()
def spreadsheet_list_aliases(
    ctx: Context,
    doc_name: str,
    sheet_name: str,
) -> CallToolResult:
    """List all aliases on a spreadsheet as ``{alias: address}``."""
    return spreadsheet_list_aliases_operation(
        get_freecad_connection(), state.only_text_feedback, doc_name, sheet_name
    )


@mcp.tool()
def set_expression(
    ctx: Context,
    doc_name: str,
    object_name: str,
    prop_path: str,
    expression: str,
) -> CallToolResult:
    """Bind a FreeCAD expression to an object property.

    Common ``prop_path`` values:
    - Sketch dimensional constraints: ``Constraints[3]``
    - Pad/Pocket: ``Length``, ``Length2``

    Expression examples: ``<<Dims>>.Wall``, ``<<Dims>>.PadH``.

    Returns structured JSON; on parse/bind failure returns an error (not a
    silent Invalid object).
    """
    return set_expression_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        object_name,
        prop_path,
        expression,
    )


@mcp.tool()
def clear_expression(
    ctx: Context,
    doc_name: str,
    object_name: str,
    prop_path: str,
) -> CallToolResult:
    """Clear an expression binding on an object property."""
    return clear_expression_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        object_name,
        prop_path,
    )


@mcp.tool()
def list_expressions(
    ctx: Context,
    doc_name: str,
    object_name: str,
) -> CallToolResult:
    """List ExpressionEngine bindings on an object."""
    return list_expressions_operation(
        get_freecad_connection(), state.only_text_feedback, doc_name, object_name
    )


@mcp.tool()
def body_create(
    ctx: Context,
    doc_name: str,
    body_name: str,
) -> CallToolResult:
    """Create a PartDesign::Body.

    Recommended pattern: Body → Sketch on XY_Plane → Pad → Pocket.
    """
    return body_create_operation(
        get_freecad_connection(), state.only_text_feedback, doc_name, body_name
    )


@mcp.tool()
def body_set_tip(
    ctx: Context,
    doc_name: str,
    body_name: str,
    feature_name: str,
) -> CallToolResult:
    """Set a Body's Tip to a feature (keeps the PartDesign history tip correct)."""
    return body_set_tip_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        body_name,
        feature_name,
    )


@mcp.tool()
def sketch_attach(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    support: Any,
) -> CallToolResult:
    """Attach a sketch to an origin plane or face support.

    ``support`` may be:
    - ``\"XY_Plane\"`` / ``\"XZ_Plane\"`` / ``\"YZ_Plane\"``
    - ``\"ObjectName:FaceN\"``
    - ``{\"object\": \"Obj\", \"subname\": \"Face1\"}``
    """
    return sketch_attach_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        sketch_name,
        support,
    )


@mcp.tool()
def sketch_edit_constraint(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    value: float | None = None,
    name: str | None = None,
    index: int | None = None,
) -> CallToolResult:
    """Edit a dimensional constraint by stable ``name`` (preferred) or index.

    After trim/fillet, geo indices shift — always prefer ``name``.
    """
    return sketch_edit_constraint_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        sketch_name,
        value=value,
        name=name,
        index=index,
    )


@mcp.tool()
def diagnose_parametric(
    ctx: Context,
    doc_name: str,
    object_name: str | None = None,
) -> CallToolResult:
    """Diagnose parametric / expression / sketch issues.

    Reports invalid objects, expression bind issues, and sketch constraint
    conflict/redundant/malformed summaries. Scope to one object or the whole doc.
    """
    return diagnose_parametric_operation(
        get_freecad_connection(), state.only_text_feedback, doc_name, object_name
    )


@mcp.tool()
def get_sketch_diagnostics(
    ctx: Context, doc_name: str, sketch_name: str
) -> CallToolResult:
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
def close_document(ctx: Context, doc_name: str) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
    """Return the world-frame axis-aligned bounding box of a shape.

    Link-safe: follows ``App::Link`` to the linked solid when needed and applies
    ``getGlobalPlacement()`` once (no Placement double-counting).

    Args:
        doc_name: Document containing the object.
        obj_name: Name of the shape object or Link.

    Returns:
        JSON with xmin/ymin/zmin/xmax/ymax/zmax, dx/dy/dz, and shape-source metadata.
    """
    return bounding_box_operation(get_freecad_connection(), doc_name, obj_name)


@mcp.tool()
def get_global_shape(
    ctx: Context,
    doc_name: str,
    obj_name: str,
) -> CallToolResult:
    """Resolve a world-frame shape summary for solids and App::Link objects.

    Use this when you need bbox/volume/COM without baking Placement twice.
    Follows broken/null Link proxy shapes to ``LinkedObject`` when possible.

    Args:
        doc_name: Document containing the object.
        obj_name: Object or Link name.

    Returns:
        JSON with frame=world metrics, bbox, volume, COM, and placement metadata.
    """
    return get_global_shape_operation(get_freecad_connection(), doc_name, obj_name)


@mcp.tool()
def common_volume_along_path(
    ctx: Context,
    doc_name: str,
    moving_object: str,
    obstacle_objects: list[str],
    path_object: str | None = None,
    sample_count: int = 12,
    samples: list[dict[str, Any]] | None = None,
    volume_threshold_mm3: float = 1e-6,
    stop_on_first_hit: bool = False,
) -> CallToolResult:
    """Sweep a moving solid along a path and report common volumes with obstacles.

    Provide either:
    - ``path_object`` + ``sample_count`` to sample a wire/edge path, or
    - ``samples`` as ``[{x,y,z, yaw_deg?}, ...]`` world positions for the moving
      object's global placement origin.

    Runs read-only in the isolated worker.

    Args:
        doc_name: Document containing the objects.
        moving_object: Object/Link that moves along the path.
        obstacle_objects: Objects/Links to intersect against.
        path_object: Optional wire/edge object to sample.
        sample_count: Samples along ``path_object`` (ignored when ``samples`` is set).
        samples: Explicit world-space sample points.
        volume_threshold_mm3: Minimum common volume counted as a collision.
        stop_on_first_hit: Stop sampling after the first colliding sample.

    Returns:
        JSON with per-sample common volumes and collision flags.
    """
    return common_volume_along_path_operation(
        get_freecad_connection(),
        doc_name,
        moving_object,
        obstacle_objects,
        path_object=path_object,
        sample_count=sample_count,
        samples=samples,
        volume_threshold_mm3=volume_threshold_mm3,
        stop_on_first_hit=stop_on_first_hit,
    )


@mcp.tool()
def center_of_mass(
    ctx: Context,
    doc_name: str,
    obj_name: str,
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
def create_assembly(
    ctx: Context,
    doc_name: str,
    assembly_name: str = "Assembly",
    create_joint_group: bool = True,
    recompute: bool = False,
    if_exists: Literal["error", "skip", "replace"] = "error",
) -> CallToolResult:
    """Create a built-in Assembly workbench assembly object."""
    return create_assembly_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        assembly_name,
        create_joint_group,
        recompute,
        if_exists,
    )


@mcp.tool()
def create_assembly_grounded_joint(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    component_name: str,
    label: str | None = None,
    recompute: bool = True,
) -> CallToolResult:
    """Ground an assembly component through the headless Assembly API."""
    return create_assembly_grounded_joint_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        assembly_name,
        component_name,
        label,
        recompute,
    )


@mcp.tool()
def create_assembly_joint(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    joint_type: Literal[
        "Fixed",
        "Revolute",
        "Cylindrical",
        "Slider",
        "Ball",
        "Distance",
        "Parallel",
        "Perpendicular",
        "Angle",
        "RackPinion",
        "Screw",
        "Gears",
        "Belt",
    ],
    ref1_component: str,
    ref2_component: str,
    ref1_element: str = "",
    ref2_element: str = "",
    ref1_vertex: str | None = None,
    ref2_vertex: str | None = None,
    label: str | None = None,
    solve: bool = True,
    presolve: bool = True,
    recompute: bool = True,
    properties: dict[str, Any] | None = None,
) -> CallToolResult:
    """Create a built-in Assembly joint from two component subelement references."""
    return create_assembly_joint_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        assembly_name,
        joint_type,
        ref1_component,
        ref2_component,
        ref1_element,
        ref2_element,
        ref1_vertex,
        ref2_vertex,
        label,
        solve,
        presolve,
        recompute,
        properties,
    )


@mcp.tool()
def create_part_container(
    ctx: Context,
    doc_name: str,
    part_name: str,
    parent_container: str | None = None,
    if_exists: Literal["error", "skip", "replace"] = "error",
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
    """Create a PartDesign datum plane for assembly reference workflows.

    Recipes (avoid the silent P1/P3 traps):
      * **XY_Plane + AttachmentOffset instead of a rotated datum.** Prefer
        attaching to an origin ``XY_Plane``/``XZ_Plane``/``YZ_Plane`` and using
        ``offset_along_normal`` + ``AttachmentOffset`` to position the plane,
        rather than creating a datum on a default axis and then rotating its
        Placement. A rotated ``Deactivated`` datum can drop the rotation (P3).
      * **Identity-body rebuild for cross-body datums.** When a datum in Body A
        must reference a face in Body B, keep Body B at an identity placement
        (move the geometry into Body B via a pad/transform instead of moving the
        body). FreeCAD's attacher can drop a non-identity source-body placement
        (P1). Use ``preview_attachment`` to confirm, and ``placement_audit`` to
        find risk concentrations.
    """
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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
) -> CallToolResult:
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


@mcp.tool()
def preview_attachment(
    ctx: Context, doc_name: str, datum_name: str
) -> CallToolResult:
    """Preview an existing datum's attachment — a read-only P1 diagnostic.

    Reports the support reference, the support face/edge global centre and
    normal, the datum's global base/normal, the owning bodies and their
    placements, ``source_body_placement_dropped`` (True when the support lives
    in a different body with a non-identity placement — the cross-body
    attachment drop risk), and a signed distance + normal-angle diff between the
    datum and its support.

    Use this BEFORE building geometry on a cross-body datum, and to debug a
    datum that landed in the wrong place, instead of rebuilding the model.

    Args:
        doc_name: The document containing the datum.
        datum_name: The name of the datum (PartDesign::Plane/Line/Point, or any
            object with an AttachmentSupport) to inspect.
    """
    return preview_attachment_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        datum_name,
    )


@mcp.tool()
def find_faces(
    ctx: Context,
    doc_name: str,
    object_name: str,
    type: str | None = None,
    normal_approx: dict | list | None = None,
    center_approx: dict | list | None = None,
    radius: float | None = None,
    tol: float = 1e-3,
    center_tol: float = 1.0,
    limit: int = 10,
) -> CallToolResult:
    """Find faces of an object by geometry — removes face-index fragility (I4).

    Returns a ranked JSON list of faces matching the criteria, each with its
    global centre, global normal, area and radius. Ask for "the top planar face"
    (``type='Plane', normal_approx={'x':0,'y':0,'z':1}``) instead of guessing
    ``Face6``.

    Args:
        doc_name: The document containing the object.
        object_name: The object whose faces to search.
        type: Optional surface type filter: 'Plane', 'Cylinder', 'Cone',
            'Sphere', 'Toroid'.
        normal_approx: Optional {'x','y','z'} (or [x,y,z]) vector; faces whose
            normal is parallel to this within ``tol`` are kept.
        center_approx: Optional point; faces whose global centre is within
            ``center_tol`` mm of it are kept, and results are ranked by closeness.
        radius: Optional radius; cylindrical/spherical faces within ``tol`` are kept.
        tol: Parallelism and radius tolerance (default 1e-3).
        center_tol: Centre proximity tolerance in mm (default 1.0).
        limit: Maximum number of results (default 10).
    """
    return find_faces_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        object_name,
        type=type,
        normal_approx=normal_approx,
        center_approx=center_approx,
        radius=radius,
        tol=tol,
        center_tol=center_tol,
        limit=limit,
    )


@mcp.tool()
def find_edges(
    ctx: Context,
    doc_name: str,
    object_name: str,
    type: str | None = None,
    direction_approx: dict | list | None = None,
    center_approx: dict | list | None = None,
    radius: float | None = None,
    tol: float = 1e-3,
    center_tol: float = 1.0,
    limit: int = 10,
) -> CallToolResult:
    """Find edges of an object by geometry — removes edge-index fragility (I4).

    Returns a ranked JSON list of edges matching the criteria, each with its
    global centre, global direction, length and radius. E.g. find the circular
    edge of radius 5 on top of a cylinder with
    ``type='Circle', radius=5, center_approx={'x':0,'y':0,'z':10}``.

    Args:
        doc_name: The document containing the object.
        object_name: The object whose edges to search.
        type: Optional curve type filter: 'Line', 'Circle', 'Ellipse',
            'BSplineCurve'.
        direction_approx: Optional vector; edges whose axis is parallel to this
            within ``tol`` are kept (use for line edges).
        center_approx: Optional point; edges whose global centre is within
            ``center_tol`` mm are kept, results ranked by closeness.
        radius: Optional radius; circular/elliptical edges within ``tol`` are kept.
        tol: Parallelism and radius tolerance (default 1e-3).
        center_tol: Centre proximity tolerance in mm (default 1.0).
        limit: Maximum number of results (default 10).
    """
    return find_edges_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        object_name,
        type=type,
        direction_approx=direction_approx,
        center_approx=center_approx,
        radius=radius,
        tol=tol,
        center_tol=center_tol,
        limit=limit,
    )


@mcp.tool()
def face_normal(
    ctx: Context, doc_name: str, object_name: str, face: str
) -> CallToolResult:
    """Return the global normal (and centre) of a face (M6 / P8 guard).

    Derives the vector from the face geometry via ``normalAt`` rotated by the
    object's global placement, avoiding the Direction-vs-Axis trap. Returns JSON
    ``{ok, object, subshape, type, global_center, global_normal, radius}``.

    Args:
        doc_name: The document containing the object.
        object_name: The object whose face to inspect.
        face: The face name, e.g. ``"Face3"``.
    """
    return face_normal_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        object_name,
        face,
    )


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
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        object_name,
        edge,
    )


@mcp.tool()
def placement_audit(
    ctx: Context, doc_name: str
) -> CallToolResult:
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
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
    )


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
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        owner_body,
        name,
        source,
        relative=relative,
        bind_mode=bind_mode,
    )


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
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        owner_body,
        name,
        source,
        relative=relative,
        offset=offset,
    )


@mcp.tool()
def run_transaction(
    ctx: Context,
    doc_name: str,
    label: str,
    code: str,
    dry_run: bool = False,
    commit_on_success: bool = True,
) -> CallToolResult:
    """Run code inside ``openTransaction`` with automatic rollback on failure (M5)."""
    return run_transaction_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        label,
        code,
        dry_run=dry_run,
        commit_on_success=commit_on_success,
    )


@mcp.tool()
def validate_movement_follow(
    ctx: Context,
    doc_name: str,
    source: str,
    dependents: list[str],
    translation: list[float],
    axis: list[float],
    angle_deg: float,
    restore: bool = True,
    tolerance: float = 1e-7,
) -> CallToolResult:
    """Validate that dependents follow a source body under an arbitrary rigid transform (M7)."""
    return validate_movement_follow_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        source,
        dependents,
        translation,
        axis,
        angle_deg,
        restore=restore,
        tolerance=tolerance,
    )


@mcp.tool()
def audit_hardcoded_dimensions(
    ctx: Context,
    doc_name: str,
    body_name: str,
    flag_aliases: bool = True,
) -> CallToolResult:
    """Report driving dimensions in a body that lack expressions (M8)."""
    return audit_hardcoded_dimensions_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        body_name,
        flag_aliases=flag_aliases,
    )


@mcp.tool()
def inspect_geometry(
    ctx: Context,
    doc_name: str,
    object_name: str,
    subshape: str | None = None,
    activate: bool = False,
    restore_active_document: bool = True,
) -> CallToolResult:
    """Normalized local/global geometry inspection for any object type (M10/M11)."""
    return inspect_geometry_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        object_name,
        subshape=subshape,
        activate=activate,
        restore_active_document=restore_active_document,
    )


@mcp.tool()
def get_dependency_graph(
    ctx: Context,
    doc_name: str,
    root: str,
) -> CallToolResult:
    """Property-annotated dependency graph from a root object (M13)."""
    return get_dependency_graph_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        root,
    )


@mcp.tool()
def match_subshape(
    ctx: Context,
    doc_name: str,
    source_object: str,
    source_subshape: str,
    target_object: str,
    limit: int = 10,
    tolerance: float = 1.0,
) -> CallToolResult:
    """Rank target subshapes by semantic similarity to a source subshape (M14)."""
    return match_subshape_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        source_object,
        source_subshape,
        target_object,
        limit=limit,
        tolerance=tolerance,
    )


@mcp.tool()
def relink_references(
    ctx: Context, doc_name: str, from_obj: str, to_obj: str
) -> CallToolResult:
    """Re-point every reference to ``from_obj`` so it points to ``to_obj`` (M5).

    Scans all link-type properties (AttachmentSupport, Support, Profile, Base,
    Tool, Source, Group, ...) of all document objects and re-points them, making
    rebuilds non-destructive. Subshape names are preserved; mismatches surface
    via the recompute log. Returns JSON ``{ok, from, to, relinked, count}``.

    Args:
        doc_name: The document to edit.
        from_obj: The object whose references are being redirected away from.
        to_obj: The object references should now point to.
    """
    return relink_references_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        from_obj,
        to_obj,
    )


@mcp.tool()
def capture_state(
    ctx: Context, doc_name: str, object_names: list[str] | None = None
) -> CallToolResult:
    """Capture a compact geometric state for a set of objects (I10 / P10).

    Records each object's placement, bounding box and face/edge counts. Pass the
    returned JSON to ``geometric_diff`` to produce a text-only diff when a
    viewable image can't be returned.

    Args:
        doc_name: The document to capture.
        object_names: Optional list of object names; all objects when None.
    """
    return capture_state_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        object_names,
    )


@mcp.tool()
def geometric_diff(
    ctx: Context,
    doc_name: str,
    before: dict,
    object_names: list[str] | None = None,
) -> CallToolResult:
    """Structured geometric diff between a captured ``before`` state and now (I10).

    The P10 text-only fallback: returns JSON
    ``{ok, doc, diffs: [{name, bbox_before/after, placement_before/after,
    faces_added/removed, changed}]}`` when a viewable image can't be returned.

    Args:
        doc_name: The document to diff against.
        before: A state dict previously returned by ``capture_state``.
        object_names: Optional list of object names; all objects when None.
    """
    return geometric_diff_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        before,
        object_names,
    )


@mcp.tool()
def snapshot(ctx: Context, doc_name: str) -> CallToolResult:
    """Snapshot the current document into a ring buffer of the last 5 states (I7).

    Cheap, in-process document copy so a risky step can be undone with one
    ``restore`` call. Returns JSON ``{ok, snapshot_id, doc, count}``.

    Args:
        doc_name: The document to snapshot.
    """
    return snapshot_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
    )


@mcp.tool()
def restore(
    ctx: Context, doc_name: str, snapshot_id: str | None = None
) -> CallToolResult:
    """Restore a snapshot, replacing the current document in place (I7).

    If ``snapshot_id`` is omitted, the most recent snapshot is restored. The
    current document is closed and the snapshot file is reopened, so the
    document is restored in place. Returns JSON
    ``{ok, restored_id, doc, new_doc, count}``.

    Args:
        doc_name: The document to restore into (replaced in place).
        snapshot_id: Optional snapshot id returned by ``snapshot``; latest if omitted.
    """
    return restore_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        snapshot_id,
    )


@mcp.tool()
def solve_assembly(
    ctx: Context, doc_name: str, assembly_name: str
) -> CallToolResult:
    """Re-solve an Assembly after editing a joint or a referenced face (I9 / P9).

    Tries ``assembly.solve()`` (C++), then ``JointObject.solveIfAllowed``, then a
    plain recompute, and reports which method succeeded. Returns JSON
    ``{ok, assembly, method, status}`` plus a screenshot.

    Args:
        doc_name: The document containing the assembly.
        assembly_name: The name of the Assembly::AssemblyObject to solve.
    """
    return solve_assembly_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        assembly_name,
    )


@mcp.tool()
def run_fem_analysis(
    ctx: Context,
    doc_name: str,
    analysis_name: str,
    timeout: int = 600,
) -> list[TextContent | ImageContent]:
    """Run the CalculiX solver on an existing Fem::FemAnalysis container and return summary results.

    Prerequisites in the document:
    - A Part-derived solid (e.g. Part::Box, PartDesign::Body) acting as the geometry.
    - A Fem::AnalysisPython container created via `create_object`.
    - A Fem::MaterialCommon assigned to the geometry, added to the analysis.
    - A Fem::FemMeshGmsh referencing the geometry, added to the analysis (the
      mesh is generated automatically when created via `create_object`).
    - At least one Fem::ConstraintFixed and one Fem::ConstraintForce (or
      ConstraintPressure) bound to faces of the geometry, added to the analysis.

    A SolverCcxTools is auto-created if the analysis has none.

    The solver runs synchronously on the FreeCAD GUI thread and blocks all
    other RPC calls for its duration; do not fan out parallel requests.

    Returns max von Mises stress (MPa), max/min displacement (mm), node count,
    and the working directory CalculiX wrote to. On failure, returns the
    prerequisite-check or solver error along with the working directory for
    triage.

    Args:
        doc_name: Name of the FreeCAD document.
        analysis_name: Name of the Fem::AnalysisPython object.
        timeout: Seconds to wait for the solver (default 600).
    """
    return run_fem_analysis_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        analysis_name,
        timeout,
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
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--only-text-feedback", action="store_true", help="Only return text feedback")
    # The addon's RPC server binds IPv4 only, but "localhost" resolves to ::1 first on
    # Windows, costing ~2s per call to fail over to IPv4. Dial IPv4 directly.
    parser.add_argument("--host", type=_validate_host, default="127.0.0.1", help="Host address of the FreeCAD RPC server to connect to (default: 127.0.0.1)")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="RPC port of the FreeCAD addon (default: FREECAD_MCP_PORT or 9875)",
    )
    parser.add_argument(
        "--instance-id",
        type=str,
        default=None,
        help=(
            "Expected FreeCAD instance id (default: FREECAD_MCP_INSTANCE_ID). When "
            "set, the client verifies the addon on --port reports the same id "
            "before driving it -- use it to pin an isolated parallel instance."
        ),
    )
    args = parser.parse_args()
    state.only_text_feedback = args.only_text_feedback
    state.rpc_host = args.host
    if args.port is not None:
        state.rpc_port = int(args.port)
    else:
        env_port = os.environ.get("FREECAD_MCP_PORT")
        if env_port:
            state.rpc_port = int(env_port)
    state.instance_id = args.instance_id or os.environ.get("FREECAD_MCP_INSTANCE_ID") or None
    logger.info(f"Only text feedback: {state.only_text_feedback}")
    logger.info(
        f"Connecting to FreeCAD RPC server at: {state.rpc_host}:{state.rpc_port}"
        + (f" (instance {state.instance_id})" if state.instance_id else "")
    )
    mcp.run()
