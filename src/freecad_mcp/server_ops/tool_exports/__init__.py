"""Explicit §3.3 MCP tool export bindings for server façade."""

from __future__ import annotations

from .bind_part_1 import (
    bind_default_export_namespace as _bind_part_1_namespace,
)
from .bind_part_1 import (
    bind_tool_exports_part_1,
)
from .bind_part_2 import (
    bind_default_export_namespace as _bind_part_2_namespace,
)
from .bind_part_2 import (
    bind_tool_exports_part_2,
)
from .export_names import __all__ as __all__

_compatibility_for_manifest = None
_runtime_info_payload = None
acquire_document_lock = None
activate_document = None
adopt_dirty_document = None
animate_placement = None
audit_hardcoded_dimensions = None
body_create = None
body_set_tip = None
boolean_difference = None
boolean_intersection = None
boolean_union = None
bounding_box = None
build_path_wire = None
cancel_request = None
cancel_worker_job = None
capture_state = None
center_of_mass = None
chamfer_feature = None
check_gear_pair = None
check_rpc_sync = None
claim_acquisition_result = None
clear_expression = None
close_document = None
common_volume_along_path = None
compare_documents = None
compute_gear_geometry = None
create_assembly = None
create_assembly_grounded_joint = None
create_assembly_joint = None
create_datum_plane = None
create_document = None
create_helical_gear = None
create_involute_gear = None
create_object = None
create_part_container = None
create_placement_binder = None
create_placement_datum = None
create_spur_gear = None
create_subshape_binder = None
delete_object = None
diagnose_helix = None
diagnose_parametric = None
diagnose_pocket = None
edge_axis = None
edit_object = None
encode_view_video = None
execute_code = None
execute_code_async = None
export_brep = None
export_step = None
export_stl = None
face_normal = None
fillet_feature = None
finalize_document_edit = None
find_edges = None
find_faces = None
force_release_stale_lock = None
geometric_diff = None
get_dependency_graph = None
get_document_lock = None
get_document_tree = None
get_global_shape = None
get_gui_state = None
get_object = None
get_objects = None
get_parts_list = None
get_recompute_log = None
get_request_status = None
get_runtime_info = None
get_selection = None
get_sketch_diagnostics = None
get_sketch_geometry = None
get_view = None
get_worker_status = None
heartbeat_document_lock = None
helical_sweep_feature = None
import_brep = None
import_step = None
insert_part_from_library = None
inspect_geometry = None
inspect_references = None
linear_pattern_feature = None
list_document_locks = None
list_documents = None
list_expressions = None
loft_feature = None
match_subshape = None
measure_angle = None
measure_area = None
measure_distance = None
measure_volume = None
mirror_feature = None
move_object = None
open_document = None
pad_feature = None
placement_audit = None
pocket_feature = None
polar_pattern_feature = None
preview_attachment = None
recompute_and_wait = None
recompute_document = None
redo = None
refresh_view = None
release_document_lock = None
relink_references = None
reload_document = None
repair_references = None
repair_view_placements = None
restore = None
revolve_feature = None
rotate = None
run_fem_analysis = None
run_transaction = None
save_document = None
save_document_as = None
save_view_sequence = None
scale = None
select_subshapes = None
set_color = None
set_expression = None
set_section_view = None
set_tree_expanded = None
sketch_add_arc = None
sketch_add_arc_of_ellipse = None
sketch_add_bezier = None
sketch_add_bspline = None
sketch_add_bspline_through_points = None
sketch_add_circle = None
sketch_add_constraint = None
sketch_add_ellipse = None
sketch_add_external_projection = None
sketch_add_geometry = None
sketch_add_line = None
sketch_add_parametric_curve = None
sketch_add_polyline = None
sketch_add_rectangle = None
sketch_add_regular_polygon = None
sketch_add_slot = None
sketch_attach = None
sketch_constrain_coincident = None
sketch_constrain_distance = None
sketch_constrain_equal = None
sketch_constrain_horizontal = None
sketch_constrain_parallel = None
sketch_constrain_perpendicular = None
sketch_constrain_radius = None
sketch_constrain_tangent = None
sketch_constrain_vertical = None
sketch_create = None
sketch_delete_constraint = None
sketch_delete_geometry = None
sketch_edit_constraint = None
sketch_extend = None
sketch_fillet = None
sketch_import_points = None
sketch_split = None
sketch_symmetry = None
sketch_toggle_construction = None
sketch_trim = None
snapshot = None
solve_assembly = None
spreadsheet_create = None
spreadsheet_get_cells = None
spreadsheet_list_aliases = None
spreadsheet_set_alias = None
spreadsheet_set_cells = None
sweep_feature = None
sweep_pipe = None
translate = None
undo = None
update_document_lock = None
validate_geometry = None
validate_movement_follow = None

_bind_part_1_namespace(globals())
_bind_part_2_namespace(globals())


def bind_tool_exports(exports: dict[str, object]) -> None:
    """Assign explicit tool exports for monkeypatch-friendly §3.3 shims."""
    namespace = globals()
    bind_tool_exports_part_1(exports, namespace)
    bind_tool_exports_part_2(exports, namespace)
