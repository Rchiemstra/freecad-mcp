"""p7_assembly.py (thin façade; §3.3 shims)."""

from __future__ import annotations

from .p7_assembly_ops.assembly_ops import (
    create_assembly_grounded_joint_operation,
    create_assembly_joint_operation,
    create_assembly_operation,
    solve_assembly_operation,
)
from .p7_assembly_ops.document_tree_ops import (
    create_datum_plane_operation,
    create_part_container_operation,
    create_subshape_binder_operation,
    get_document_tree_operation,
    move_object_operation,
)
from .p7_assembly_ops.helpers import (
    _PREFLIGHT_SENTINEL,
    _doc_preamble,
    _extract_execute_output,
    _extract_preflight,
    _run_json_code,
    _shared_helpers,
    _validate_if_exists,
)
from .p7_assembly_ops.path_ops import (
    build_path_wire_operation,
    sweep_pipe_operation,
)
from .p7_assembly_ops.sketch_projection_ops import (
    get_sketch_geometry_operation,
    sketch_add_external_projection_operation,
)

__all__ = [
    "_PREFLIGHT_SENTINEL",
    "_doc_preamble",
    "_extract_execute_output",
    "_extract_preflight",
    "_run_json_code",
    "_shared_helpers",
    "_validate_if_exists",
    "build_path_wire_operation",
    "create_assembly_grounded_joint_operation",
    "create_assembly_joint_operation",
    "create_assembly_operation",
    "create_datum_plane_operation",
    "create_part_container_operation",
    "create_subshape_binder_operation",
    "get_document_tree_operation",
    "get_sketch_geometry_operation",
    "move_object_operation",
    "sketch_add_external_projection_operation",
    "solve_assembly_operation",
    "sweep_pipe_operation",
]
