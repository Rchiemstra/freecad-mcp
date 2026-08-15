"""core.py (thin façade; §3.3 shims)."""

from __future__ import annotations

from .core_ops.code_gen import (
    _build_assertion_code,
    _constraint_line,
    _constraint_stmt,
    _geom_line,
    _indented_build_assertion,
    _partdesign_bool_property_helper_code,
    _partdesign_extrusion_helper_code,
    _partdesign_pattern_helper_code,
)
from .core_ops.document_ops import (
    close_document_operation,
    create_document_operation,
    list_documents_operation,
    recompute_document_operation,
    reload_document_operation,
)
from .core_ops.execute_ops import (
    execute_code_async_operation,
    execute_code_operation,
    get_view_operation,
    save_view_sequence_operation,
)
from .core_ops.feature_ops import (
    create_spur_gear_operation,
    linear_pattern_feature_operation,
    mirror_feature_operation,
    pad_feature_operation,
    pocket_feature_operation,
    polar_pattern_feature_operation,
)
from .core_ops.fem_ops import run_fem_analysis_operation
from .core_ops.history_ops import (
    get_mutation_readiness_operation,
    redo_operation,
    undo_operation,
)
from .core_ops.object_ops import (
    create_object_operation,
    delete_object_operation,
    edit_object_operation,
    get_object_operation,
    get_objects_operation,
    get_parts_list_operation,
)
from .core_ops.read_diagnostics_ops import (
    get_recompute_log_operation,
    get_sketch_diagnostics_operation,
)
from .core_ops.recompute_log import (
    _RECOMPUTE_LOG_SENTINEL,
    _format_recompute_log,
)
from .core_ops.reference_ops import (
    insert_part_from_library_operation,
    inspect_references_operation,
    repair_references_operation,
)
from .core_ops.run_code import _run_code
from .core_ops.sketch_constraint_ops import (
    _run_constraint,
    sketch_add_arc_operation,
    sketch_add_circle_operation,
    sketch_add_line_operation,
    sketch_add_rectangle_operation,
    sketch_constrain_coincident_operation,
    sketch_constrain_distance_operation,
    sketch_constrain_equal_operation,
    sketch_constrain_horizontal_operation,
    sketch_constrain_parallel_operation,
    sketch_constrain_perpendicular_operation,
    sketch_constrain_radius_operation,
    sketch_constrain_tangent_operation,
    sketch_constrain_vertical_operation,
)
from .core_ops.sketch_ops import (
    sketch_add_constraint_operation,
    sketch_add_geometry_operation,
    sketch_create_operation,
    sketch_delete_constraint_operation,
    sketch_delete_geometry_operation,
)

__all__ = [
    "_RECOMPUTE_LOG_SENTINEL",
    "_build_assertion_code",
    "_constraint_line",
    "_constraint_stmt",
    "_format_recompute_log",
    "_geom_line",
    "_indented_build_assertion",
    "_partdesign_bool_property_helper_code",
    "_partdesign_extrusion_helper_code",
    "_partdesign_pattern_helper_code",
    "_run_code",
    "_run_constraint",
    "close_document_operation",
    "create_document_operation",
    "create_object_operation",
    "create_spur_gear_operation",
    "delete_object_operation",
    "edit_object_operation",
    "execute_code_async_operation",
    "execute_code_operation",
    "get_mutation_readiness_operation",
    "get_object_operation",
    "get_objects_operation",
    "get_parts_list_operation",
    "get_recompute_log_operation",
    "get_sketch_diagnostics_operation",
    "get_view_operation",
    "insert_part_from_library_operation",
    "inspect_references_operation",
    "linear_pattern_feature_operation",
    "list_documents_operation",
    "mirror_feature_operation",
    "pad_feature_operation",
    "pocket_feature_operation",
    "polar_pattern_feature_operation",
    "recompute_document_operation",
    "redo_operation",
    "reload_document_operation",
    "repair_references_operation",
    "run_fem_analysis_operation",
    "save_view_sequence_operation",
    "sketch_add_arc_operation",
    "sketch_add_circle_operation",
    "sketch_add_constraint_operation",
    "sketch_add_geometry_operation",
    "sketch_add_line_operation",
    "sketch_add_rectangle_operation",
    "sketch_constrain_coincident_operation",
    "sketch_constrain_distance_operation",
    "sketch_constrain_equal_operation",
    "sketch_constrain_horizontal_operation",
    "sketch_constrain_parallel_operation",
    "sketch_constrain_perpendicular_operation",
    "sketch_constrain_radius_operation",
    "sketch_constrain_tangent_operation",
    "sketch_constrain_vertical_operation",
    "sketch_create_operation",
    "sketch_delete_constraint_operation",
    "sketch_delete_geometry_operation",
    "undo_operation",
]
