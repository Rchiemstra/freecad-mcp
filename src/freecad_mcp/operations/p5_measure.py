"""p5_measure.py (thin façade; §3.3 shims)."""

from __future__ import annotations

from .p5_measure_ops.measure_ops import (
    _doc_sk_preamble,
    _run_read_analysis,
    bounding_box_operation,
    center_of_mass_operation,
    common_volume_along_path_operation,
    get_global_shape_operation,
    measure_angle_operation,
    measure_area_operation,
    measure_distance_operation,
    measure_volume_operation,
    rotate_operation,
    scale_operation,
    translate_operation,
    validate_geometry_operation,
)

__all__ = [
    "_doc_sk_preamble",
    "_run_read_analysis",
    "bounding_box_operation",
    "center_of_mass_operation",
    "common_volume_along_path_operation",
    "get_global_shape_operation",
    "measure_angle_operation",
    "measure_area_operation",
    "measure_distance_operation",
    "measure_volume_operation",
    "rotate_operation",
    "scale_operation",
    "translate_operation",
    "validate_geometry_operation",
]
