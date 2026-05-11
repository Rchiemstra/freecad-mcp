"""
P3 — 3-D feature operations: revolve, loft, sweep, helix, fillet, chamfer, booleans.
"""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse
from .core import _run_code, _partdesign_pattern_helper_code

logger = logging.getLogger("FreeCADMCPserver")


def _doc_preamble(doc_name: str) -> list[str]:
    return [
        "import FreeCAD, Part, math",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"if not _doc: raise RuntimeError({f'Document {doc_name!r} not found'!r})",
    ]


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
    lines = _doc_preamble(doc_name) + [
        f"_sk = _doc.getObject({sketch_name!r})",
        "if not _sk: raise RuntimeError('Sketch not found')",
        *_partdesign_pattern_helper_code(),
    ]
    if body_name:
        lines += [
            f"_body = _doc.getObject({body_name!r})",
            "if not _body: raise RuntimeError('Body not found')",
        ]
    else:
        lines += [
            "_body = None",
            "for _o in _doc.Objects:",
            "    if _o.TypeId == 'PartDesign::Body' and _sk in getattr(_o,'Group',[]): _body = _o; break",
        ]
    lines += [
        f"_rev = _body.newObject('PartDesign::Revolution', {revolve_name!r}) if _body else _doc.addObject('PartDesign::Revolution', {revolve_name!r})",
        "_rev.Profile = (_sk, [''])",
        f"_rev.Angle = {angle}",
        f"_set_linksub(_rev, ('ReferenceAxis', 'Axis'), _resolve_linksub(_doc, _body, {axis!r}))",
        f"_rev.Symmetric = {symmetric}",
        f"_rev.Reversed = {reversed_dir}",
        "_sk.Visibility = False",
        "_doc.recompute()",
        "print('revolve_name=' + _rev.Name)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Revolution '{revolve_name}' created", "Failed to create revolution")


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
    lines = _doc_preamble(doc_name)
    if body_name:
        lines += [
            f"_body = _doc.getObject({body_name!r})",
            "if not _body: raise RuntimeError('Body not found')",
        ]
    else:
        lines += ["_body = None"]
    lines += [
        f"_sk_names = {repr(sketch_names)}",
        "_profiles = [(_doc.getObject(_n), ['']) for _n in _sk_names]",
        "if any(_p[0] is None for _p in _profiles): raise RuntimeError('One or more sketches not found')",
        f"_loft = _body.newObject('PartDesign::AdditiveLoft', {loft_name!r}) if _body else _doc.addObject('PartDesign::AdditiveLoft', {loft_name!r})",
        "_loft.Sections = _profiles",
        f"_loft.Ruled = {ruled}",
        f"_loft.Closed = {closed}",
        "_doc.recompute()",
        "print('loft_name=' + _loft.Name)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Loft '{loft_name}' created", "Failed to create loft")


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
    lines = _doc_preamble(doc_name) + [
        f"_profile = _doc.getObject({profile_sketch!r})",
        f"_path = _doc.getObject({path_sketch!r})",
        "if not _profile: raise RuntimeError('Profile sketch not found')",
        "if not _path: raise RuntimeError('Path sketch not found')",
    ]
    if body_name:
        lines += [f"_body = _doc.getObject({body_name!r})", "if not _body: raise RuntimeError('Body not found')"]
    else:
        lines += ["_body = None", "for _o in _doc.Objects:", "    if _o.TypeId == 'PartDesign::Body' and _profile in getattr(_o,'Group',[]): _body = _o; break"]
    lines += [
        f"_sw = _body.newObject('PartDesign::AdditivePipe', {sweep_name!r}) if _body else _doc.addObject('PartDesign::AdditivePipe', {sweep_name!r})",
        "_sw.Profile = (_profile, [''])",
        "_sw.Spine = (_path, [''])",
        f"_sw.Frenet = {frenet}",
        "_doc.recompute()",
        "print('sweep_name=' + _sw.Name)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Sweep '{sweep_name}' created", "Failed to create sweep")


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
    lines = _doc_preamble(doc_name) + [
        f"_profile = _doc.getObject({profile_sketch!r})",
        "if not _profile: raise RuntimeError('Profile sketch not found')",
    ]
    if body_name:
        lines += [f"_body = _doc.getObject({body_name!r})", "if not _body: raise RuntimeError('Body not found')"]
    else:
        lines += ["_body = None", "for _o in _doc.Objects:", "    if _o.TypeId == 'PartDesign::Body' and _profile in getattr(_o,'Group',[]): _body = _o; break"]
    lines += [
        f"_hel = _body.newObject('PartDesign::AdditiveHelix', {helix_name!r}) if _body else _doc.addObject('PartDesign::AdditiveHelix', {helix_name!r})",
        "_hel.Profile = (_profile, [''])",
        f"_hel.Pitch = {pitch}",
        f"_hel.Height = {height}",
        f"_hel.Radius = {radius}",
        f"_hel.LeftHanded = {left_handed}",
        f"_hel.Reversed = {reversed_dir}",
        "_doc.recompute()",
        "print('helix_name=' + _hel.Name)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Helical sweep '{helix_name}' created", "Failed to create helical sweep")


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
    edge_str = repr(edge_refs or [])
    lines = _doc_preamble(doc_name) + [
        f"_base = _doc.getObject({base_feature!r})",
        "if not _base: raise RuntimeError('Base feature not found')",
    ]
    if body_name:
        lines += [f"_body = _doc.getObject({body_name!r})", "if not _body: raise RuntimeError('Body not found')"]
    else:
        lines += ["_body = None", "for _o in _doc.Objects:", "    if _o.TypeId == 'PartDesign::Body' and _base in getattr(_o,'Group',[]): _body = _o; break"]
    lines += [
        f"_fil = _body.newObject('PartDesign::Fillet', {fillet_name!r}) if _body else _doc.addObject('PartDesign::Fillet', {fillet_name!r})",
        "_fil.Base = (_base, [])",
        f"_fil.Radius = {radius}",
        f"_edge_refs = {edge_str}",
        "if _edge_refs:",
        "    _fil.Base = (_base, _edge_refs)",
        "_doc.recompute()",
        "print('fillet_name=' + _fil.Name)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Fillet '{fillet_name}' (r={radius}) created", "Failed to create fillet")


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
    edge_str = repr(edge_refs or [])
    lines = _doc_preamble(doc_name) + [
        f"_base = _doc.getObject({base_feature!r})",
        "if not _base: raise RuntimeError('Base feature not found')",
    ]
    if body_name:
        lines += [f"_body = _doc.getObject({body_name!r})", "if not _body: raise RuntimeError('Body not found')"]
    else:
        lines += ["_body = None", "for _o in _doc.Objects:", "    if _o.TypeId == 'PartDesign::Body' and _base in getattr(_o,'Group',[]): _body = _o; break"]
    lines += [
        f"_chm = _body.newObject('PartDesign::Chamfer', {chamfer_name!r}) if _body else _doc.addObject('PartDesign::Chamfer', {chamfer_name!r})",
        "_chm.Base = (_base, [])",
        f"_chm.Size = {size}",
        f"_edge_refs = {edge_str}",
        "if _edge_refs:",
        "    _chm.Base = (_base, _edge_refs)",
        "_doc.recompute()",
        "print('chamfer_name=' + _chm.Name)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Chamfer '{chamfer_name}' (s={size}) created", "Failed to create chamfer")


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
    lines = _doc_preamble(doc_name) + [
        f"_s1 = _doc.getObject({shape1!r})",
        f"_s2 = _doc.getObject({shape2!r})",
        "if not _s1: raise RuntimeError('Shape1 not found')",
        "if not _s2: raise RuntimeError('Shape2 not found')",
        f"_bool = _doc.addObject({fc_type!r}, {result_name!r})",
        "_bool.Base = _s1",
        "_bool.Tool = _s2",
        "_s1.Visibility = False",
        "_s2.Visibility = False",
        "_doc.recompute()",
        "print('result_name=' + _bool.Name)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Boolean {bool_type} '{result_name}' created",
                     f"Failed to create boolean {bool_type}")


def boolean_union_operation(freecad, only_text_feedback, doc_name, shape1, shape2, result_name):
    return _boolean_operation(freecad, only_text_feedback, doc_name, shape1, shape2, result_name, "union")


def boolean_difference_operation(freecad, only_text_feedback, doc_name, shape1, shape2, result_name):
    return _boolean_operation(freecad, only_text_feedback, doc_name, shape1, shape2, result_name, "difference")


def boolean_intersection_operation(freecad, only_text_feedback, doc_name, shape1, shape2, result_name):
    return _boolean_operation(freecad, only_text_feedback, doc_name, shape1, shape2, result_name, "intersection")
