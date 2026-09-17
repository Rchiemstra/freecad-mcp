"""Static imports for typed RPC handler leaf modules."""

from __future__ import annotations

from . import activate_document as _mod_activate_document
from . import audit_hardcoded_dimensions as _mod_audit_hardcoded_dimensions
from . import body_create as _mod_body_create
from . import body_set_tip as _mod_body_set_tip
from . import boolean_difference as _mod_boolean_difference
from . import boolean_intersection as _mod_boolean_intersection
from . import boolean_union as _mod_boolean_union
from . import bounding_box as _mod_bounding_box
from . import build_path_wire as _mod_build_path_wire
from . import capture_state as _mod_capture_state
from . import center_of_mass as _mod_center_of_mass
from . import chamfer_feature as _mod_chamfer_feature
from . import clear_expression as _mod_clear_expression
from . import close_document as _mod_close_document
from . import common_volume_along_path as _mod_common_volume_along_path
from . import create_assembly as _mod_create_assembly
from . import create_assembly_grounded_joint as _mod_create_assembly_grounded_joint
from . import create_assembly_joint as _mod_create_assembly_joint
from . import create_datum_plane as _mod_create_datum_plane
from . import create_document as _mod_create_document
from . import create_helical_gear as _mod_create_helical_gear
from . import create_involute_gear as _mod_create_involute_gear
from . import create_object as _mod_create_object
from . import create_part_container as _mod_create_part_container
from . import create_placement_binder as _mod_create_placement_binder
from . import create_placement_datum as _mod_create_placement_datum
from . import create_spur_gear as _mod_create_spur_gear
from . import create_subshape_binder as _mod_create_subshape_binder
from . import delete_object as _mod_delete_object
from . import diagnose_helix as _mod_diagnose_helix
from . import diagnose_parametric as _mod_diagnose_parametric
from . import diagnose_pocket as _mod_diagnose_pocket
from . import edge_axis as _mod_edge_axis
from . import edit_object as _mod_edit_object
from . import export_brep as _mod_export_brep
from . import export_step as _mod_export_step
from . import export_stl as _mod_export_stl
from . import face_normal as _mod_face_normal
from . import fillet_feature as _mod_fillet_feature
from . import find_edges as _mod_find_edges
from . import find_faces as _mod_find_faces
from . import get_dependency_graph as _mod_get_dependency_graph
from . import get_document_tree as _mod_get_document_tree
from . import get_global_shape as _mod_get_global_shape
from . import get_object as _mod_get_object
from . import get_recompute_log as _mod_get_recompute_log
from . import get_sketch_diagnostics as _mod_get_sketch_diagnostics
from . import get_sketch_geometry as _mod_get_sketch_geometry
from . import helical_sweep_feature as _mod_helical_sweep_feature
from . import import_brep as _mod_import_brep
from . import import_step as _mod_import_step
from . import insert_part_from_library as _mod_insert_part_from_library
from . import inspect_geometry as _mod_inspect_geometry
from . import linear_pattern_feature as _mod_linear_pattern_feature
from . import list_expressions as _mod_list_expressions
from . import loft_feature as _mod_loft_feature
from . import match_subshape as _mod_match_subshape
from . import measure_angle as _mod_measure_angle
from . import measure_area as _mod_measure_area
from . import measure_distance as _mod_measure_distance
from . import measure_volume as _mod_measure_volume
from . import mirror_feature as _mod_mirror_feature
from . import move_object as _mod_move_object
from . import open_document as _mod_open_document
from . import pad_feature as _mod_pad_feature
from . import placement_audit as _mod_placement_audit
from . import pocket_feature as _mod_pocket_feature
from . import polar_pattern_feature as _mod_polar_pattern_feature
from . import preview_attachment as _mod_preview_attachment
from . import recompute_and_wait as _mod_recompute_and_wait
from . import recompute_document as _mod_recompute_document
from . import redo as _mod_redo
from . import relink_references as _mod_relink_references
from . import reload_document as _mod_reload_document
from . import repair_references as _mod_repair_references
from . import restore as _mod_restore
from . import revolve_feature as _mod_revolve_feature
from . import rotate as _mod_rotate
from . import run_fem_analysis as _mod_run_fem_analysis
from . import run_transaction as _mod_run_transaction
from . import scale as _mod_scale
from . import set_color as _mod_set_color
from . import set_expression as _mod_set_expression
from . import sketch_add_arc as _mod_sketch_add_arc
from . import sketch_add_arc_of_ellipse as _mod_sketch_add_arc_of_ellipse
from . import sketch_add_bezier as _mod_sketch_add_bezier
from . import sketch_add_bspline as _mod_sketch_add_bspline
from . import sketch_add_bspline_through_points as _mod_sketch_add_bspline_through_points
from . import sketch_add_circle as _mod_sketch_add_circle
from . import sketch_add_constraint as _mod_sketch_add_constraint
from . import sketch_add_ellipse as _mod_sketch_add_ellipse
from . import sketch_add_external_projection as _mod_sketch_add_external_projection
from . import sketch_add_geometry as _mod_sketch_add_geometry
from . import sketch_add_line as _mod_sketch_add_line
from . import sketch_add_parametric_curve as _mod_sketch_add_parametric_curve
from . import sketch_add_polyline as _mod_sketch_add_polyline
from . import sketch_add_rectangle as _mod_sketch_add_rectangle
from . import sketch_add_regular_polygon as _mod_sketch_add_regular_polygon
from . import sketch_add_slot as _mod_sketch_add_slot
from . import sketch_attach as _mod_sketch_attach
from . import sketch_constrain_coincident as _mod_sketch_constrain_coincident
from . import sketch_constrain_distance as _mod_sketch_constrain_distance
from . import sketch_constrain_equal as _mod_sketch_constrain_equal
from . import sketch_constrain_horizontal as _mod_sketch_constrain_horizontal
from . import sketch_constrain_parallel as _mod_sketch_constrain_parallel
from . import sketch_constrain_perpendicular as _mod_sketch_constrain_perpendicular
from . import sketch_constrain_radius as _mod_sketch_constrain_radius
from . import sketch_constrain_tangent as _mod_sketch_constrain_tangent
from . import sketch_constrain_vertical as _mod_sketch_constrain_vertical
from . import sketch_create as _mod_sketch_create
from . import sketch_delete_constraint as _mod_sketch_delete_constraint
from . import sketch_delete_geometry as _mod_sketch_delete_geometry
from . import sketch_edit_constraint as _mod_sketch_edit_constraint
from . import sketch_extend as _mod_sketch_extend
from . import sketch_fillet as _mod_sketch_fillet
from . import sketch_import_points as _mod_sketch_import_points
from . import sketch_offset as _mod_sketch_offset
from . import sketch_split as _mod_sketch_split
from . import sketch_symmetry as _mod_sketch_symmetry
from . import sketch_toggle_construction as _mod_sketch_toggle_construction
from . import sketch_trim as _mod_sketch_trim
from . import snapshot as _mod_snapshot
from . import solve_assembly as _mod_solve_assembly
from . import spreadsheet_create as _mod_spreadsheet_create
from . import spreadsheet_get_cells as _mod_spreadsheet_get_cells
from . import spreadsheet_list_aliases as _mod_spreadsheet_list_aliases
from . import spreadsheet_set_alias as _mod_spreadsheet_set_alias
from . import spreadsheet_set_cells as _mod_spreadsheet_set_cells
from . import sweep_feature as _mod_sweep_feature
from . import sweep_pipe as _mod_sweep_pipe
from . import translate as _mod_translate
from . import undo as _mod_undo
from . import validate_geometry as _mod_validate_geometry
from . import validate_movement_follow as _mod_validate_movement_follow

_HANDLER_MODULES = (
    _mod_activate_document,
    _mod_audit_hardcoded_dimensions,
    _mod_body_create,
    _mod_body_set_tip,
    _mod_boolean_difference,
    _mod_boolean_intersection,
    _mod_boolean_union,
    _mod_bounding_box,
    _mod_build_path_wire,
    _mod_capture_state,
    _mod_center_of_mass,
    _mod_chamfer_feature,
    _mod_clear_expression,
    _mod_close_document,
    _mod_common_volume_along_path,
    _mod_create_assembly,
    _mod_create_assembly_grounded_joint,
    _mod_create_assembly_joint,
    _mod_create_datum_plane,
    _mod_create_document,
    _mod_create_helical_gear,
    _mod_create_involute_gear,
    _mod_create_object,
    _mod_create_part_container,
    _mod_create_placement_binder,
    _mod_create_placement_datum,
    _mod_create_spur_gear,
    _mod_create_subshape_binder,
    _mod_delete_object,
    _mod_diagnose_helix,
    _mod_diagnose_parametric,
    _mod_diagnose_pocket,
    _mod_edge_axis,
    _mod_edit_object,
    _mod_export_brep,
    _mod_export_step,
    _mod_export_stl,
    _mod_face_normal,
    _mod_fillet_feature,
    _mod_find_edges,
    _mod_find_faces,
    _mod_get_dependency_graph,
    _mod_get_document_tree,
    _mod_get_global_shape,
    _mod_get_object,
    _mod_get_recompute_log,
    _mod_get_sketch_diagnostics,
    _mod_get_sketch_geometry,
    _mod_helical_sweep_feature,
    _mod_import_brep,
    _mod_import_step,
    _mod_insert_part_from_library,
    _mod_inspect_geometry,
    _mod_linear_pattern_feature,
    _mod_list_expressions,
    _mod_loft_feature,
    _mod_match_subshape,
    _mod_measure_angle,
    _mod_measure_area,
    _mod_measure_distance,
    _mod_measure_volume,
    _mod_mirror_feature,
    _mod_move_object,
    _mod_open_document,
    _mod_pad_feature,
    _mod_placement_audit,
    _mod_pocket_feature,
    _mod_polar_pattern_feature,
    _mod_preview_attachment,
    _mod_recompute_and_wait,
    _mod_recompute_document,
    _mod_redo,
    _mod_relink_references,
    _mod_reload_document,
    _mod_repair_references,
    _mod_restore,
    _mod_revolve_feature,
    _mod_rotate,
    _mod_run_fem_analysis,
    _mod_run_transaction,
    _mod_scale,
    _mod_set_color,
    _mod_set_expression,
    _mod_sketch_add_arc,
    _mod_sketch_add_arc_of_ellipse,
    _mod_sketch_add_bezier,
    _mod_sketch_add_bspline,
    _mod_sketch_add_bspline_through_points,
    _mod_sketch_add_circle,
    _mod_sketch_add_constraint,
    _mod_sketch_add_ellipse,
    _mod_sketch_add_external_projection,
    _mod_sketch_add_geometry,
    _mod_sketch_add_line,
    _mod_sketch_add_parametric_curve,
    _mod_sketch_add_polyline,
    _mod_sketch_add_rectangle,
    _mod_sketch_add_regular_polygon,
    _mod_sketch_add_slot,
    _mod_sketch_attach,
    _mod_sketch_constrain_coincident,
    _mod_sketch_constrain_distance,
    _mod_sketch_constrain_equal,
    _mod_sketch_constrain_horizontal,
    _mod_sketch_constrain_parallel,
    _mod_sketch_constrain_perpendicular,
    _mod_sketch_constrain_radius,
    _mod_sketch_constrain_tangent,
    _mod_sketch_constrain_vertical,
    _mod_sketch_create,
    _mod_sketch_delete_constraint,
    _mod_sketch_delete_geometry,
    _mod_sketch_edit_constraint,
    _mod_sketch_extend,
    _mod_sketch_fillet,
    _mod_sketch_import_points,
    _mod_sketch_offset,
    _mod_sketch_split,
    _mod_sketch_symmetry,
    _mod_sketch_toggle_construction,
    _mod_sketch_trim,
    _mod_snapshot,
    _mod_solve_assembly,
    _mod_spreadsheet_create,
    _mod_spreadsheet_get_cells,
    _mod_spreadsheet_list_aliases,
    _mod_spreadsheet_set_alias,
    _mod_spreadsheet_set_cells,
    _mod_sweep_feature,
    _mod_sweep_pipe,
    _mod_translate,
    _mod_undo,
    _mod_validate_geometry,
    _mod_validate_movement_follow,
)

__all__ = ["_HANDLER_MODULES"]
