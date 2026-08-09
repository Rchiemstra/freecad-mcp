"""
P5 — Measurement, validation, and transform operations.
"""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse
from ..template_resources import render_template_lines, render_template_text
from .core import _run_code

logger = logging.getLogger("FreeCADMCPserver")


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


# ---------------------------------------------------------------------------
# P5-1  measure_distance
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# P5-2  measure_angle
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# P5-3  measure_area
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# P5-4  measure_volume
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# P5-5  bounding_box
# ---------------------------------------------------------------------------

def bounding_box_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    code = render_template_text("p5_measure/bounding_box.py.txt", obj_name=repr(obj_name))
    lines = _doc_sk_preamble(doc_name) + code.strip().splitlines()
    return _run_read_analysis(freecad, doc_name, "\n".join(lines),
                              f"Bounding box of '{obj_name}'", "Failed to get bounding box")


# ---------------------------------------------------------------------------
# P5-5b  get_global_shape
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# P5-5c  common_volume_along_path
# ---------------------------------------------------------------------------

def common_volume_along_path_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    moving_object: str,
    obstacle_objects: list[str],
    *,
    path_object: str | None = None,
    sample_count: int = 12,
    samples: list[dict] | None = None,
    volume_threshold_mm3: float = 1e-6,
    stop_on_first_hit: bool = False,
) -> ToolResponse:
    """Sweep a moving solid along a path and report common volumes with obstacles."""
    if not obstacle_objects:
        from ..responses import tool_fail
        return tool_fail("obstacle_objects must contain at least one object name")
    if not samples and not path_object:
        from ..responses import tool_fail
        return tool_fail("Provide samples (list of {x,y,z}) or path_object")
    lines = _doc_sk_preamble(doc_name) + render_template_lines(
        "p5_measure/common_volume_along_path.py.txt",
        moving_object=repr(moving_object),
        obstacle_objects=repr(list(obstacle_objects)),
        path_object=repr(path_object),
        sample_count=repr(int(sample_count)),
        samples=repr(samples),
        volume_threshold_mm3=repr(float(volume_threshold_mm3)),
        stop_on_first_hit=repr(bool(stop_on_first_hit)),
    )
    return _run_read_analysis(
        freecad,
        doc_name,
        "\n".join(lines),
        f"Common-volume path sweep of '{moving_object}'",
        "Failed common-volume path sweep",
    )


# ---------------------------------------------------------------------------
# P5-6  center_of_mass
# ---------------------------------------------------------------------------

def center_of_mass_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + render_template_lines(
        "p5_measure/center_of_mass.py.txt",
        obj_name=repr(obj_name),
    )
    return _run_read_analysis(freecad, doc_name, "\n".join(lines),
                              f"Centre of mass of '{obj_name}'", "Failed to get centre of mass")


# ---------------------------------------------------------------------------
# P5-7  validate_geometry
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# P5-8  translate
# ---------------------------------------------------------------------------

def translate_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    dx: float,
    dy: float,
    dz: float,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + render_template_lines(
        "p5_measure/translate.py.txt",
        obj_name=repr(obj_name),
        dx=repr(dx),
        dy=repr(dy),
        dz=repr(dz),
        message=repr(f"translated {obj_name} by ({dx},{dy},{dz})"),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Object '{obj_name}' translated by ({dx},{dy},{dz})",
                     "Failed to translate", document=doc_name)


# ---------------------------------------------------------------------------
# P5-9  rotate
# ---------------------------------------------------------------------------

def rotate_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    axis_x: float,
    axis_y: float,
    axis_z: float,
    angle_deg: float,
    center_x: float = 0.0,
    center_y: float = 0.0,
    center_z: float = 0.0,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + render_template_lines(
        "p5_measure/rotate.py.txt",
        obj_name=repr(obj_name),
        axis_x=repr(axis_x),
        axis_y=repr(axis_y),
        axis_z=repr(axis_z),
        center_x=repr(center_x),
        center_y=repr(center_y),
        center_z=repr(center_z),
        angle_deg=repr(angle_deg),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Object '{obj_name}' rotated {angle_deg}° about axis",
                     "Failed to rotate", document=doc_name)


# ---------------------------------------------------------------------------
# P5-10  scale
# ---------------------------------------------------------------------------

def scale_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    sx: float,
    sy: float,
    sz: float,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + render_template_lines(
        "p5_measure/scale.py.txt",
        obj_name=repr(obj_name),
        sx=repr(sx),
        sy=repr(sy),
        sz=repr(sz),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Object '{obj_name}' scaled by ({sx},{sy},{sz})",
                     "Failed to scale", document=doc_name)
