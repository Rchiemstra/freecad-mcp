"""Inspection, validation, repair, and recovery-oriented operations. (thin façade; §3.3 shims)."""

from __future__ import annotations

from .diagnostics_ops.attachment_ops import preview_attachment_operation
from .diagnostics_ops.audit_ops import (
    audit_hardcoded_dimensions_operation,
    get_dependency_graph_operation,
    inspect_geometry_operation,
    match_subshape_operation,
)
from .diagnostics_ops.mutation_ops import (
    create_placement_binder_operation,
    create_placement_datum_operation,
    run_transaction_operation,
    validate_movement_follow_operation,
)
from .diagnostics_ops.placement_ops import (
    _diff_states,
    geometric_diff_operation,
    placement_audit_operation,
)
from .parametric_ops.capture_state import capture_state_operation
from .parametric_ops.relink_references import relink_references_operation
from .diagnostics_ops.subshape_ops import (
    edge_axis_operation,
    face_normal_operation,
    find_edges_operation,
    find_faces_operation,
    subshape_pose_operation,
)

__all__ = [
    "_diff_states",
    "audit_hardcoded_dimensions_operation",
    "capture_state_operation",
    "create_placement_binder_operation",
    "create_placement_datum_operation",
    "edge_axis_operation",
    "face_normal_operation",
    "find_edges_operation",
    "find_faces_operation",
    "geometric_diff_operation",
    "get_dependency_graph_operation",
    "inspect_geometry_operation",
    "match_subshape_operation",
    "placement_audit_operation",
    "preview_attachment_operation",
    "relink_references_operation",
    "run_transaction_operation",
    "subshape_pose_operation",
    "validate_movement_follow_operation",
]
