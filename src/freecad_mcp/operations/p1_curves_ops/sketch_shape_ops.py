from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import tool_fail
from ...template_resources import render_template_lines
from ..core_ops.run_code import _run_code
from .helpers import _sk_preamble


def sketch_add_ellipse_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    cx: float,
    cy: float,
    major_radius: float,
    minor_radius: float,
    angle: float = 0.0,
    construction: bool = False,
) -> ToolResponse:
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p1_curves/sketch_add_ellipse.py.txt",
        angle=repr(angle),
        cx=repr(cx),
        cy=repr(cy),
        major_radius=repr(major_radius),
        minor_radius=repr(minor_radius),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Ellipse added to '{sketch_name}'", "Failed to add ellipse",
                     document=doc_name)


def sketch_add_arc_of_ellipse_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    cx: float,
    cy: float,
    major_radius: float,
    minor_radius: float,
    start_angle: float,
    end_angle: float,
    angle: float = 0.0,
    construction: bool = False,
) -> ToolResponse:
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p1_curves/sketch_add_arc_of_ellipse.py.txt",
        angle=repr(angle),
        cx=repr(cx),
        cy=repr(cy),
        major_radius=repr(major_radius),
        minor_radius=repr(minor_radius),
        start_angle=repr(start_angle),
        end_angle=repr(end_angle),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Arc of ellipse added to '{sketch_name}'", "Failed to add arc of ellipse",
                     document=doc_name)


def sketch_add_slot_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    width: float,
    construction: bool = False,
) -> ToolResponse:
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p1_curves/sketch_add_slot.py.txt",
        x1=repr(x1),
        y1=repr(y1),
        x2=repr(x2),
        y2=repr(y2),
        width=repr(width),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Slot added to '{sketch_name}'", "Failed to add slot",
                     document=doc_name)


def sketch_add_regular_polygon_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    cx: float,
    cy: float,
    radius: float,
    sides: int,
    angle: float = 0.0,
    construction: bool = False,
) -> ToolResponse:
    if sides < 3:
        return tool_fail(
            "regular polygon requires at least 3 sides",
            error_code="INVALID_ARGUMENT",
        )
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p1_curves/sketch_add_regular_polygon.py.txt",
        cx=repr(cx),
        cy=repr(cy),
        radius=repr(radius),
        sides=repr(sides),
        angle=repr(angle),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Regular polygon ({sides} sides) added to '{sketch_name}'",
                     "Failed to add regular polygon", document=doc_name)


def sketch_add_parametric_curve_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    x_expr: str,
    y_expr: str,
    t_start: float,
    t_end: float,
    samples: int = 100,
    construction: bool = False,
) -> ToolResponse:
    if samples < 10 or samples > 2000:
        return tool_fail(
            "samples must be between 10 and 2000",
            error_code="INVALID_ARGUMENT",
        )
    if t_start >= t_end:
        return tool_fail(
            "t_start must be less than t_end",
            error_code="INVALID_ARGUMENT",
        )
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p1_curves/sketch_add_parametric_curve.py.txt",
        t_start=repr(t_start),
        t_end=repr(t_end),
        samples=repr(samples),
        x_expr=x_expr,
        y_expr=y_expr,
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Parametric curve added to '{sketch_name}'",
                     "Failed to add parametric curve", document=doc_name)


def sketch_import_points_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    points: list[dict],
    construction: bool = False,
) -> ToolResponse:
    pt_str = "[" + ",".join(f"({p['x']},{p['y']})" for p in points) + "]"
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p1_curves/sketch_import_points.py.txt",
        points=pt_str,
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"{len(points)} point(s) imported to '{sketch_name}'",
                     "Failed to import points", document=doc_name)


def sketch_toggle_construction_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo_indices: list[int],
    construction: bool = True,
) -> ToolResponse:
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p1_curves/sketch_toggle_construction.py.txt",
        geo_indices=repr(geo_indices),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Construction mode set on {geo_indices} in '{sketch_name}'",
                     "Failed to toggle construction", document=doc_name)
