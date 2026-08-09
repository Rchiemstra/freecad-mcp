"""Inspection, validation, repair, and recovery-oriented operations. (thin façade; §3.3 shims)."""

from __future__ import annotations

from .diagnostics_ops.attachment_ops import preview_attachment_operation
from .diagnostics_ops.audit_ops import (
    audit_hardcoded_dimensions_operation,
    get_dependency_graph_operation,
    inspect_geometry_operation,
    match_subshape_operation,
)
from .diagnostics_ops.helpers import (
    _diag_preamble,
    _response_text,
)
from .diagnostics_ops.mutation_ops import (
    create_placement_binder_operation,
    create_placement_datum_operation,
    run_transaction_operation,
    validate_movement_follow_operation,
)
from .diagnostics_ops.placement_ops import (
    _diff_states,
    capture_state_operation,
    geometric_diff_operation,
    placement_audit_operation,
    relink_references_operation,
)
from .diagnostics_ops.subshape_ops import (
    _find_subshapes_operation,
    _subshape_pose_operation,
    edge_axis_operation,
    face_normal_operation,
    find_edges_operation,
    find_faces_operation,
)

__all__ = [
    "_diag_preamble",
    "_diff_states",
    "_find_subshapes_operation",
    "_response_text",
    "_subshape_pose_operation",
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
    "validate_movement_follow_operation",
]
