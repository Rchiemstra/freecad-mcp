"""
P1 — Sketch curve operations.

All tools use the execute_code pattern so they work without addon updates.
"""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse
from ..template_resources import render_template_lines
from .core import _run_code

logger = logging.getLogger("FreeCADMCPserver")

def _sk_preamble(doc_name: str, sketch_name: str) -> list[str]:
    return render_template_lines(
        "p1_curves/sk_preamble.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
    )


# ---------------------------------------------------------------------------
# P1-1  sketch_add_polyline
# ---------------------------------------------------------------------------

def sketch_add_polyline_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    points: list[dict],
    closed: bool = False,
    construction: bool = False,
) -> ToolResponse:
    if len(points) < 2:
        from ..responses import text_response
        return text_response("polyline requires at least 2 points")
    c = repr(construction)
    segment_lines = []
    pts = [(p["x"], p["y"]) for p in points]
    if closed and pts[-1] != pts[0]:
        pts = pts + [pts[0]]
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        segment_lines.append(
            f"_idxs.append(_sk.addGeometry(Part.LineSegment("
            f"FreeCAD.Vector({x1},{y1},0),FreeCAD.Vector({x2},{y2},0)),{c}))"
        )
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p1_curves/sketch_add_polyline.py.txt",
        segment_lines="\n".join(segment_lines),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Polyline added to '{sketch_name}'", "Failed to add polyline",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P1-2  sketch_add_bspline
# ---------------------------------------------------------------------------

def sketch_add_bspline_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    poles: list[dict],
    degree: int = 3,
    weights: list[float] | None = None,
    knots: list[float] | None = None,
    multiplicities: list[int] | None = None,
    periodic: bool = False,
    construction: bool = False,
) -> ToolResponse:
    c = repr(construction)
    per = repr(periodic)
    pole_str = "[" + ",".join(f"FreeCAD.Vector({p['x']},{p['y']},0)" for p in poles) + "]"
    w_str = repr(weights) if weights else repr([1.0] * len(poles))
    if knots and multiplicities:
        k_str = repr(knots)
        m_str = repr(multiplicities)
        build_line = f"_bsp.buildFromPolesMultsKnots(_poles, {m_str}, {k_str}, _periodic, _degree, _weights)"
    else:
        build_line = "_bsp.buildFromPoles(_poles, _periodic, _degree)"
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p1_curves/sketch_add_bspline.py.txt",
        poles=pole_str,
        weights=w_str,
        degree=repr(degree),
        periodic=per,
        build_line=build_line,
        construction=c,
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"BSpline added to '{sketch_name}'", "Failed to add BSpline",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P1-3  sketch_add_bspline_through_points
# ---------------------------------------------------------------------------

def sketch_add_bspline_through_points_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    points: list[dict],
    degree: int = 3,
    periodic: bool = False,
    construction: bool = False,
) -> ToolResponse:
    c = repr(construction)
    per = repr(periodic)
    pt_str = "[" + ",".join(f"FreeCAD.Vector({p['x']},{p['y']},0)" for p in points) + "]"
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p1_curves/sketch_add_bspline_through_points.py.txt",
        points=pt_str,
        periodic=per,
        construction=c,
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Interpolating BSpline added to '{sketch_name}'",
                     "Failed to add interpolating BSpline", document=doc_name)


# ---------------------------------------------------------------------------
# P1-4  sketch_add_bezier
# ---------------------------------------------------------------------------

def sketch_add_bezier_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    poles: list[dict],
    construction: bool = False,
) -> ToolResponse:
    c = repr(construction)
    pole_str = "[" + ",".join(f"FreeCAD.Vector({p['x']},{p['y']},0)" for p in poles) + "]"
    lines = _sk_preamble(doc_name, sketch_name) + render_template_lines(
        "p1_curves/sketch_add_bezier.py.txt",
        poles=pole_str,
        construction=c,
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Bezier curve added to '{sketch_name}'", "Failed to add Bezier curve",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P1-5  sketch_add_ellipse
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# P1-6  sketch_add_arc_of_ellipse
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# P1-7  sketch_add_slot
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# P1-8  sketch_add_regular_polygon
# ---------------------------------------------------------------------------

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
        from ..responses import text_response
        return text_response("regular polygon requires at least 3 sides")
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


# ---------------------------------------------------------------------------
# P1-9  sketch_add_parametric_curve  (KEY — drives analytic involute)
# ---------------------------------------------------------------------------

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
        from ..responses import text_response
        return text_response("samples must be between 10 and 2000")
    if t_start >= t_end:
        from ..responses import text_response
        return text_response("t_start must be less than t_end")
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


# ---------------------------------------------------------------------------
# P1-10  sketch_import_points
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# P1-11  sketch_toggle_construction
# ---------------------------------------------------------------------------

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
