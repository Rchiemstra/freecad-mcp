"""
P3 — 3-D feature operations: revolve, loft, sweep, helix, fillet, chamfer, booleans.

Public operation names stay on this module for generated tool imports. The
typed JSON-RPC implementations live in ``parametric_ops``; execute-code
templates remain in ``p3_features_legacy``.
"""
from __future__ import annotations

from .parametric_ops.boolean_difference import boolean_difference_operation
from .parametric_ops.boolean_intersection import boolean_intersection_operation
from .parametric_ops.boolean_union import boolean_union_operation
from .parametric_ops.chamfer_feature import chamfer_feature_operation
from .parametric_ops.fillet_feature import fillet_feature_operation
from .parametric_ops.helical_sweep_feature import helical_sweep_feature_operation
from .parametric_ops.loft_feature import loft_feature_operation
from .parametric_ops.revolve_feature import revolve_feature_operation
from .parametric_ops.sweep_feature import sweep_feature_operation

__all__ = [
    "boolean_difference_operation",
    "boolean_intersection_operation",
    "boolean_union_operation",
    "chamfer_feature_operation",
    "fillet_feature_operation",
    "helical_sweep_feature_operation",
    "loft_feature_operation",
    "revolve_feature_operation",
    "sweep_feature_operation",
]
