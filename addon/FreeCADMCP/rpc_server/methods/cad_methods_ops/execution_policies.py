"""Execution policy registry for CAD RPC handlers (addon-side mirror)."""

from __future__ import annotations

from enum import StrEnum

# ruff: noqa: E501


class ExecutionPolicy(StrEnum):
    """CAD execution policy classification (mirrors MCP schema; no cross-package import)."""

    DOCUMENT_MUTATION = "document_mutation"
    DOCUMENT_QUERY = "document_query"
    DOCUMENT_LIFECYCLE = "document_lifecycle"
    HISTORY_OPERATION = "history_operation"
    EXTERNAL_EFFECT = "external_effect"
    GUI_GLOBAL = "gui_global"


_DOCUMENT_LIFECYCLE = (
    "activate_document",
    "close_document",
    "create_document",
    "open_document",
    "reload_document",
)

_HISTORY_OPERATION = (
    "undo",
    "redo",
)

_EXTERNAL_EFFECT = (
    "export_brep",
    "export_step",
    "export_stl",
    "run_fem_analysis",
)

_GUI_GLOBAL = (
    "animate_placement",
    "encode_view_video",
    "get_gui_state",
    "get_report_view",
    "get_selection",
    "get_view",
    "refresh_view",
    "repair_view_placements",
    "save_view_sequence",
    "select_subshapes",
    "set_color",
    "set_section_view",
    "set_tree_expanded",
)

_DOCUMENT_QUERY = (
    "audit_hardcoded_dimensions",
    "bounding_box",
    "capture_state",
    "center_of_mass",
    "check_gear_pair",
    "common_volume_along_path",
    "compare_documents",
    "compute_gear_geometry",
    "diagnose_helix",
    "diagnose_parametric",
    "diagnose_pocket",
    "edge_axis",
    "face_normal",
    "find_edges",
    "find_faces",
    "geometric_diff",
    "get_dependency_graph",
    "get_document_tree",
    "get_global_shape",
    "get_object",
    "get_objects",
    "get_parts_list",
    "get_recompute_log",
    "get_sketch_diagnostics",
    "get_sketch_geometry",
    "inspect_geometry",
    "inspect_references",
    "list_documents",
    "list_expressions",
    "match_subshape",
    "measure_angle",
    "measure_area",
    "measure_distance",
    "measure_volume",
    "placement_audit",
    "snapshot",
    "spreadsheet_get_cells",
    "spreadsheet_list_aliases",
    "validate_geometry",
)

_DOCUMENT_MUTATION = (
    "body_create",
    "body_set_tip",
    "boolean_difference",
    "boolean_intersection",
    "boolean_union",
    "build_path_wire",
    "chamfer_feature",
    "clear_expression",
    "create_assembly",
    "create_assembly_grounded_joint",
    "create_assembly_joint",
    "create_datum_plane",
    "create_helical_gear",
    "create_involute_gear",
    "create_object",
    "create_part_container",
    "create_placement_binder",
    "create_placement_datum",
    "create_spur_gear",
    "create_subshape_binder",
    "delete_object",
    "edit_object",
    "fillet_feature",
    "helical_sweep_feature",
    "import_brep",
    "import_step",
    "insert_part_from_library",
    "linear_pattern_feature",
    "loft_feature",
    "mirror_feature",
    "move_object",
    "pad_feature",
    "pocket_feature",
    "polar_pattern_feature",
    "preview_attachment",
    "recompute_and_wait",
    "recompute_document",
    "relink_references",
    "repair_references",
    "restore",
    "run_transaction",
    "revolve_feature",
    "rotate",
    "scale",
    "set_expression",
    "sketch_add_arc",
    "sketch_add_arc_of_ellipse",
    "sketch_add_bezier",
    "sketch_add_bspline",
    "sketch_add_bspline_through_points",
    "sketch_add_circle",
    "sketch_add_constraint",
    "sketch_add_ellipse",
    "sketch_add_external_projection",
    "sketch_add_geometry",
    "sketch_add_line",
    "sketch_add_parametric_curve",
    "sketch_add_polyline",
    "sketch_add_rectangle",
    "sketch_add_regular_polygon",
    "sketch_add_slot",
    "sketch_attach",
    "sketch_constrain_coincident",
    "sketch_constrain_distance",
    "sketch_constrain_equal",
    "sketch_constrain_horizontal",
    "sketch_constrain_parallel",
    "sketch_constrain_perpendicular",
    "sketch_constrain_radius",
    "sketch_constrain_tangent",
    "sketch_constrain_vertical",
    "sketch_create",
    "sketch_delete_constraint",
    "sketch_delete_geometry",
    "sketch_edit_constraint",
    "sketch_extend",
    "sketch_fillet",
    "sketch_import_points",
    "sketch_offset",
    "sketch_split",
    "sketch_symmetry",
    "sketch_toggle_construction",
    "sketch_trim",
    "solve_assembly",
    "spreadsheet_create",
    "spreadsheet_set_alias",
    "spreadsheet_set_cells",
    "sweep_feature",
    "sweep_pipe",
    "translate",
    "validate_movement_follow",
)

EXECUTION_POLICIES: dict[str, ExecutionPolicy] = {
    **{name: ExecutionPolicy.DOCUMENT_LIFECYCLE for name in _DOCUMENT_LIFECYCLE},
    **{name: ExecutionPolicy.HISTORY_OPERATION for name in _HISTORY_OPERATION},
    **{name: ExecutionPolicy.EXTERNAL_EFFECT for name in _EXTERNAL_EFFECT},
    **{name: ExecutionPolicy.GUI_GLOBAL for name in _GUI_GLOBAL},
    **{name: ExecutionPolicy.DOCUMENT_QUERY for name in _DOCUMENT_QUERY},
    **{name: ExecutionPolicy.DOCUMENT_MUTATION for name in _DOCUMENT_MUTATION},
}


def policy_for(name: str) -> ExecutionPolicy:
    """Return the execution policy for a CAD RPC name."""

    try:
        return EXECUTION_POLICIES[name]
    except KeyError as exc:
        raise KeyError(f"no execution policy registered for {name!r}") from exc


__all__ = [
    "EXECUTION_POLICIES",
    "ExecutionPolicy",
    "policy_for",
]
