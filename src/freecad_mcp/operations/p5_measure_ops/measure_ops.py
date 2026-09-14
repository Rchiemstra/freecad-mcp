from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_lines
from ..core_ops.run_code import _run_code
from ..parametric_ops.bounding_box import bounding_box_operation
from ..parametric_ops.center_of_mass import center_of_mass_operation
from ..parametric_ops.common_volume_along_path import common_volume_along_path_operation
from ..parametric_ops.rotate import rotate_operation
from ..parametric_ops.scale import scale_operation
from ..parametric_ops.translate import translate_operation

def _run_read_analysis(
    freecad: FreeCADConnection,
    doc_name: str,
    code: str,
    success_msg: str,
    fail_prefix: str,
) -> ToolResponse:
    """Geometry measurements run explicitly in the isolated snapshot worker."""
    return _run_code(
        freecad,
        True,
        code,
        success_msg,
        fail_prefix,
        document=doc_name,
        recompute="none",
        capture_view=False,
        read_only=True,
        execution_mode="worker",
    )

def _doc_sk_preamble(doc_name: str) -> list[str]:
    return render_template_lines(
        "p5_measure/doc_preamble.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
    ) + render_template_lines("p5_measure/shape_helpers.py.txt")

def measure_distance_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    shape1_ref: str,
    shape2_ref: str,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + render_template_lines(
        "p5_measure/measure_distance.py.txt",
        shape1_ref=repr(shape1_ref),
        shape2_ref=repr(shape2_ref),
    )
    return _run_read_analysis(freecad, doc_name, "\n".join(lines),
                              f"Distance between '{shape1_ref}' and '{shape2_ref}'",
                              "Failed to measure distance")

def measure_angle_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    edge1_ref: str,
    edge2_ref: str,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + render_template_lines(
        "p5_measure/measure_angle.py.txt",
        edge1_ref=repr(edge1_ref),
        edge2_ref=repr(edge2_ref),
    )
    return _run_read_analysis(freecad, doc_name, "\n".join(lines),
                              f"Angle between '{edge1_ref}' and '{edge2_ref}'",
                              "Failed to measure angle")

def measure_area_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + render_template_lines(
        "p5_measure/measure_area.py.txt",
        obj_name=repr(obj_name),
    )
    return _run_read_analysis(freecad, doc_name, "\n".join(lines),
                              f"Surface area of '{obj_name}'", "Failed to measure area")

def measure_volume_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + render_template_lines(
        "p5_measure/measure_volume.py.txt",
        obj_name=repr(obj_name),
    )
    return _run_read_analysis(freecad, doc_name, "\n".join(lines),
                              f"Volume of '{obj_name}'", "Failed to measure volume")

def get_global_shape_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    """Return world-frame shape metrics without Placement double-counting."""
    lines = _doc_sk_preamble(doc_name) + render_template_lines(
        "p5_measure/get_global_shape.py.txt",
        obj_name=repr(obj_name),
    )
    return _run_read_analysis(
        freecad,
        doc_name,
        "\n".join(lines),
        f"Global shape of '{obj_name}'",
        "Failed to resolve global shape",
    )

def validate_geometry_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + render_template_lines(
        "p5_measure/validate_geometry.py.txt",
        obj_name=repr(obj_name),
    )
    return _run_read_analysis(freecad, doc_name, "\n".join(lines),
                              f"Geometry validation of '{obj_name}'", "Failed to validate geometry")

