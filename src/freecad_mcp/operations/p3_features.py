"""
P3 — 3-D feature operations: revolve, loft, sweep, helix, fillet, chamfer, booleans.
"""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse
from ..template_resources import render_template_lines
from .core import _build_assertion_code, _run_code, _partdesign_pattern_helper_code

logger = logging.getLogger("FreeCADMCPserver")


def _doc_preamble(doc_name: str) -> list[str]:
    return render_template_lines(
        "p3_features/doc_preamble.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
    )


# ---------------------------------------------------------------------------
# P3-1  revolve_feature
# ---------------------------------------------------------------------------

def revolve_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    revolve_name: str,
    angle: float = 360.0,
    axis: str = "Z_Axis",
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p3_features/revolve_feature.py.txt",
        sketch_name=repr(sketch_name),
        pattern_helpers="\n".join(_partdesign_pattern_helper_code()),
        body_name=repr(body_name),
        revolve_name=repr(revolve_name),
        angle=repr(angle),
        axis=repr(axis),
        symmetric=repr(symmetric),
        reversed_dir=repr(reversed_dir),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Revolution '{revolve_name}' created", "Failed to create revolution",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P3-2  loft_feature
# ---------------------------------------------------------------------------

def loft_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_names: list[str],
    loft_name: str,
    body_name: str | None = None,
    ruled: bool = False,
    closed: bool = False,
) -> ToolResponse:
    if len(sketch_names) < 2:
        from ..responses import text_response
        return text_response("loft requires at least 2 sketches")
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p3_features/loft_feature.py.txt",
        body_name=repr(body_name),
        sketch_names=repr(sketch_names),
        loft_name=repr(loft_name),
        ruled=repr(ruled),
        closed=repr(closed),
    ) + _build_assertion_code(loft_name, sketch_names[0], check_direction=False)
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Loft '{loft_name}' created", "Failed to create loft",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P3-3  sweep_feature
# ---------------------------------------------------------------------------

def sweep_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    profile_sketch: str,
    path_sketch: str,
    sweep_name: str,
    body_name: str | None = None,
    frenet: bool = False,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p3_features/sweep_feature.py.txt",
        profile_sketch=repr(profile_sketch),
        path_sketch=repr(path_sketch),
        body_name=repr(body_name),
        sweep_name=repr(sweep_name),
        frenet=repr(frenet),
    ) + _build_assertion_code(sweep_name, profile_sketch, check_direction=False)
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Sweep '{sweep_name}' created", "Failed to create sweep",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P3-4  helical_sweep_feature  (helix + profile)
# ---------------------------------------------------------------------------

def helical_sweep_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    profile_sketch: str,
    helix_name: str,
    pitch: float,
    height: float,
    radius: float,
    body_name: str | None = None,
    left_handed: bool = False,
    reversed_dir: bool = False,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p3_features/helical_sweep_feature.py.txt",
        profile_sketch=repr(profile_sketch),
        body_name=repr(body_name),
        helix_name=repr(helix_name),
        pitch=repr(pitch),
        height=repr(height),
        radius=repr(radius),
        left_handed=repr(left_handed),
        reversed_dir=repr(reversed_dir),
    ) + _build_assertion_code(helix_name, profile_sketch, check_direction=False)
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Helical sweep '{helix_name}' created", "Failed to create helical sweep",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P3-5  fillet_feature
# ---------------------------------------------------------------------------

def fillet_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    base_feature: str,
    fillet_name: str,
    radius: float,
    edge_refs: list[str] | None = None,
    body_name: str | None = None,
) -> ToolResponse:
    if radius <= 0:
        from ..responses import text_response
        return text_response("fillet radius must be > 0")
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p3_features/fillet_feature.py.txt",
        base_feature=repr(base_feature),
        body_name=repr(body_name),
        fillet_name=repr(fillet_name),
        radius=repr(radius),
        edge_refs=repr(edge_refs or []),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Fillet '{fillet_name}' (r={radius}) created", "Failed to create fillet",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P3-6  chamfer_feature
# ---------------------------------------------------------------------------

def chamfer_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    base_feature: str,
    chamfer_name: str,
    size: float,
    edge_refs: list[str] | None = None,
    body_name: str | None = None,
) -> ToolResponse:
    if size <= 0:
        from ..responses import text_response
        return text_response("chamfer size must be > 0")
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p3_features/chamfer_feature.py.txt",
        base_feature=repr(base_feature),
        body_name=repr(body_name),
        chamfer_name=repr(chamfer_name),
        size=repr(size),
        edge_refs=repr(edge_refs or []),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Chamfer '{chamfer_name}' (s={size}) created", "Failed to create chamfer",
                     document=doc_name)


# ---------------------------------------------------------------------------
# P3-7 / 8 / 9  Boolean operations
# ---------------------------------------------------------------------------

def _boolean_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    shape1: str,
    shape2: str,
    result_name: str,
    bool_type: str,
) -> ToolResponse:
    type_map = {"union": "Part::Fuse", "difference": "Part::Cut", "intersection": "Part::Common"}
    fc_type = type_map.get(bool_type, "Part::Fuse")
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p3_features/boolean_operation.py.txt",
        shape1=repr(shape1),
        shape2=repr(shape2),
        fc_type=repr(fc_type),
        result_name=repr(result_name),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Boolean {bool_type} '{result_name}' created",
                     f"Failed to create boolean {bool_type}", document=doc_name)


def boolean_union_operation(freecad, only_text_feedback, doc_name, shape1, shape2, result_name):
    return _boolean_operation(freecad, only_text_feedback, doc_name, shape1, shape2, result_name, "union")


def boolean_difference_operation(freecad, only_text_feedback, doc_name, shape1, shape2, result_name):
    return _boolean_operation(freecad, only_text_feedback, doc_name, shape1, shape2, result_name, "difference")


def boolean_intersection_operation(freecad, only_text_feedback, doc_name, shape1, shape2, result_name):
    return _boolean_operation(freecad, only_text_feedback, doc_name, shape1, shape2, result_name, "intersection")
