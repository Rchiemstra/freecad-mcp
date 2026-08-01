from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses import ToolResponse, tool_fail
from ...template_resources import render_template_lines
from ..core_ops.run_code import _run_code
from .helpers import _sk_preamble


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
        return tool_fail(
            "polyline requires at least 2 points",
            error_code="INVALID_ARGUMENT",
        )
    c = repr(construction)
    segment_lines = []
    pts = [(p["x"], p["y"]) for p in points]
    if closed and pts[-1] != pts[0]:
        pts = [*pts, pts[0]]
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
        build_line = (
            f"_bsp.buildFromPolesMultsKnots(_poles, {m_str}, {k_str}, "
            f"_periodic, _degree, _weights)"
        )
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
