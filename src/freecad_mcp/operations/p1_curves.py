"""
P1 — Sketch curve operations.

All tools use the execute_code pattern so they work without addon updates.
"""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse
from .core import _run_code

logger = logging.getLogger("FreeCADMCPserver")

_PREAMBLE = "import FreeCAD, Part, math\n"


def _sk_preamble(doc_name: str, sketch_name: str) -> list[str]:
    return [
        "import FreeCAD, Part, math",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        "if not _doc: raise RuntimeError('Document not found')",
        f"_sk = _doc.getObject({sketch_name!r})",
        "if not _sk: raise RuntimeError('Sketch not found')",
    ]


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
    c = "True" if construction else "False"
    lines = _sk_preamble(doc_name, sketch_name) + ["_idxs = []"]
    pts = [(p["x"], p["y"]) for p in points]
    if closed and pts[-1] != pts[0]:
        pts = pts + [pts[0]]
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        lines.append(
            f"_idxs.append(_sk.addGeometry(Part.LineSegment("
            f"FreeCAD.Vector({x1},{y1},0),FreeCAD.Vector({x2},{y2},0)),{c}))"
        )
    lines += ["_doc.recompute()", "print('indices=' + str(_idxs))"]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Polyline added to '{sketch_name}'", "Failed to add polyline")


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
    c = "True" if construction else "False"
    per = "True" if periodic else "False"
    pole_str = "[" + ",".join(f"FreeCAD.Vector({p['x']},{p['y']},0)" for p in poles) + "]"
    w_str = repr(weights) if weights else repr([1.0] * len(poles))
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_poles = {pole_str}",
        f"_weights = {w_str}",
        f"_degree = {degree}",
        f"_periodic = {per}",
        "_bsp = Part.BSplineCurve()",
    ]
    if knots and multiplicities:
        k_str = repr(knots)
        m_str = repr(multiplicities)
        lines += [
            f"_bsp.buildFromPolesMultsKnots(_poles, {m_str}, {k_str}, _periodic, _degree, _weights)",
        ]
    else:
        lines += [
            "_bsp.buildFromPoles(_poles, _periodic, _degree)",
        ]
    lines += [
        f"_idx = _sk.addGeometry(_bsp, {c})",
        "_doc.recompute()",
        "print('geometry_index=' + str(_idx))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"BSpline added to '{sketch_name}'", "Failed to add BSpline")


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
    c = "True" if construction else "False"
    per = "True" if periodic else "False"
    pt_str = "[" + ",".join(f"FreeCAD.Vector({p['x']},{p['y']},0)" for p in points) + "]"
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_pts = {pt_str}",
        "_bsp = Part.BSplineCurve()",
        f"_bsp.interpolate(_pts, {per})",
        f"_idx = _sk.addGeometry(_bsp, {c})",
        "_doc.recompute()",
        "print('geometry_index=' + str(_idx))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Interpolating BSpline added to '{sketch_name}'",
                     "Failed to add interpolating BSpline")


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
    c = "True" if construction else "False"
    pole_str = "[" + ",".join(f"FreeCAD.Vector({p['x']},{p['y']},0)" for p in poles) + "]"
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_poles = {pole_str}",
        "_bez = Part.BezierCurve()",
        "_bez.setPoles(_poles)",
        f"_idx = _sk.addGeometry(_bez, {c})",
        "_doc.recompute()",
        "print('geometry_index=' + str(_idx))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Bezier curve added to '{sketch_name}'", "Failed to add Bezier curve")


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
    c = "True" if construction else "False"
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_angle = math.radians({angle})",
        f"_major_pt = FreeCAD.Vector({cx} + {major_radius}*math.cos(_angle), {cy} + {major_radius}*math.sin(_angle), 0)",
        f"_center = FreeCAD.Vector({cx}, {cy}, 0)",
        f"_ell = Part.Ellipse(_major_pt, {minor_radius}, _center)",
        f"_idx = _sk.addGeometry(_ell, {c})",
        "_doc.recompute()",
        "print('geometry_index=' + str(_idx))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Ellipse added to '{sketch_name}'", "Failed to add ellipse")


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
    c = "True" if construction else "False"
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_rot = math.radians({angle})",
        f"_major_pt = FreeCAD.Vector({cx} + {major_radius}*math.cos(_rot), {cy} + {major_radius}*math.sin(_rot), 0)",
        f"_center = FreeCAD.Vector({cx}, {cy}, 0)",
        f"_ell = Part.Ellipse(_major_pt, {minor_radius}, _center)",
        f"_arc = Part.ArcOfEllipse(_ell, math.radians({start_angle}), math.radians({end_angle}))",
        f"_idx = _sk.addGeometry(_arc, {c})",
        "_doc.recompute()",
        "print('geometry_index=' + str(_idx))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Arc of ellipse added to '{sketch_name}'", "Failed to add arc of ellipse")


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
    c = "True" if construction else "False"
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_x1, _y1, _x2, _y2, _w = {x1}, {y1}, {x2}, {y2}, {width}",
        "_dx = _x2 - _x1",
        "_dy = _y2 - _y1",
        "_L = math.hypot(_dx, _dy)",
        "if _L < 1e-9: raise ValueError('slot start and end are the same point')",
        "_ux, _uy = _dx / _L, _dy / _L",
        "_px, _py = -_uy * _w / 2.0, _ux * _w / 2.0",
        "_r = _w / 2.0",
        "_idxs = []",
        # Top line
        "_idxs.append(_sk.addGeometry(Part.LineSegment("
        "FreeCAD.Vector(_x1 + _px, _y1 + _py, 0),"
        "FreeCAD.Vector(_x2 + _px, _y2 + _py, 0))," + c + "))",
        # Bottom line
        "_idxs.append(_sk.addGeometry(Part.LineSegment("
        "FreeCAD.Vector(_x2 - _px, _y2 - _py, 0),"
        "FreeCAD.Vector(_x1 - _px, _y1 - _py, 0))," + c + "))",
        # Left semicircle
        "_a1_l = math.atan2(_uy, _ux) + math.pi / 2.0",
        "_a2_l = math.atan2(_uy, _ux) + 3.0 * math.pi / 2.0",
        "_c1 = Part.Circle(FreeCAD.Vector(_x1, _y1, 0), FreeCAD.Vector(0,0,1), _r)",
        "_idxs.append(_sk.addGeometry(Part.ArcOfCircle(_c1, _a1_l, _a2_l)," + c + "))",
        # Right semicircle
        "_a1_r = math.atan2(_uy, _ux) - math.pi / 2.0",
        "_a2_r = math.atan2(_uy, _ux) + math.pi / 2.0",
        "_c2 = Part.Circle(FreeCAD.Vector(_x2, _y2, 0), FreeCAD.Vector(0,0,1), _r)",
        "_idxs.append(_sk.addGeometry(Part.ArcOfCircle(_c2, _a1_r, _a2_r)," + c + "))",
        "_doc.recompute()",
        "print('indices=' + str(_idxs))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Slot added to '{sketch_name}'", "Failed to add slot")


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
    c = "True" if construction else "False"
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_cx, _cy, _r, _n = {cx}, {cy}, {radius}, {sides}",
        f"_offset = math.radians({angle})",
        "_pts = [FreeCAD.Vector(_cx + _r*math.cos(_offset + 2*math.pi*_i/_n),"
        " _cy + _r*math.sin(_offset + 2*math.pi*_i/_n), 0) for _i in range(_n)]",
        "_idxs = []",
        "for _i in range(_n):",
        "    _idxs.append(_sk.addGeometry(Part.LineSegment(_pts[_i], _pts[(_i+1)%_n])," + c + "))",
        "_doc.recompute()",
        "print('indices=' + str(_idxs))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Regular polygon ({sides} sides) added to '{sketch_name}'",
                     "Failed to add regular polygon")


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
    c = "True" if construction else "False"
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_t0, _t1, _n = {t_start}, {t_end}, {samples}",
        "_sample_pts = []",
        "for _si in range(_n + 1):",
        "    t = _t0 + (_t1 - _t0) * _si / _n",  # 't' as loop var for the expressions
        f"    _x_val = {x_expr}",
        f"    _y_val = {y_expr}",
        "    _sample_pts.append(FreeCAD.Vector(_x_val, _y_val, 0))",
        # De-duplicate nearly coincident points (robust BSpline interpolation)
        "_unique_pts = [_sample_pts[0]]",
        "for _p in _sample_pts[1:]:",
        "    if (_p - _unique_pts[-1]).Length > 1e-9:",
        "        _unique_pts.append(_p)",
        "if len(_unique_pts) < 2:",
        "    raise ValueError('Parametric curve collapsed to a single point')",
        "_bsp = Part.BSplineCurve()",
        "_bsp.interpolate(_unique_pts)",
        f"_idx = _sk.addGeometry(_bsp, {c})",
        "_doc.recompute()",
        "print('geometry_index=' + str(_idx))",
        "print('sample_count=' + str(len(_unique_pts)))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Parametric curve added to '{sketch_name}'",
                     "Failed to add parametric curve")


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
    c = "True" if construction else "False"
    pt_str = "[" + ",".join(f"({p['x']},{p['y']})" for p in points) + "]"
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_raw_pts = {pt_str}",
        "_idxs = []",
        "for _px, _py in _raw_pts:",
        f"    _idxs.append(_sk.addGeometry(Part.Point(FreeCAD.Vector(_px, _py, 0)), {c}))",
        "_doc.recompute()",
        "print('indices=' + str(_idxs))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"{len(points)} point(s) imported to '{sketch_name}'",
                     "Failed to import points")


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
    c = "True" if construction else "False"
    idx_str = repr(geo_indices)
    lines = _sk_preamble(doc_name, sketch_name) + [
        f"_indices = {idx_str}",
        f"_construction = {c}",
        "for _gi in _indices:",
        "    _sk.toggleConstruction(_gi)",
        "    _g = _sk.Geometry[_gi]",
        "    if hasattr(_g, 'Construction') and _g.Construction != _construction:",
        "        _sk.toggleConstruction(_gi)",
        "_doc.recompute()",
        "print('toggled=' + str(_indices))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Construction mode set on {geo_indices} in '{sketch_name}'",
                     "Failed to toggle construction")
