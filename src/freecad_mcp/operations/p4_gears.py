"""
P4 — Gear library.

create_involute_gear uses the correct mathematical involute parametrization:
    x(t) = r_b * (cos(t) + t * sin(t))
    y(t) = r_b * (sin(t) - t * cos(t))

Polar angle at parameter t: θ(t) = t − atan(t)

This replaces the broken star/flower profile from create_spur_gear.
"""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse, text_response
from .core import _run_code, _partdesign_extrusion_helper_code, _partdesign_bool_property_helper_code

logger = logging.getLogger("FreeCADMCPserver")

# ---------------------------------------------------------------------------
# Shared involute code fragment (executed inside FreeCAD via execute_code)
# ---------------------------------------------------------------------------

_INVOLUTE_PROFILE_CODE = r"""
# --- True involute gear profile ---
_inv_alpha = math.tan(_pressure_angle) - _pressure_angle
_delta = math.pi / (2.0 * _teeth) - _backlash / (2.0 * _pitch_radius)

if _outer_radius <= _base_radius:
    raise ValueError(
        f"Addendum circle (r={_outer_radius:.4f}) must be larger than base circle (r={_base_radius:.4f}). "
        "Increase module or reduce pressure_angle."
    )

_t_tip  = math.sqrt((_outer_radius / _base_radius) ** 2 - 1.0)
_has_undercut = _root_radius < _base_radius
_t_root = math.sqrt((_root_radius / _base_radius) ** 2 - 1.0) if not _has_undercut else 0.0

def _ix(t):
    return _base_radius * (math.cos(t) + t * math.sin(t))
def _iy(t):
    return _base_radius * (math.sin(t) - t * math.cos(t))
def _polar(t):
    return t - math.atan(t)
def _rot(x, y, a):
    _c = math.cos(a); _s = math.sin(a)
    return _c * x - _s * y, _s * x + _c * y

for _k in range(_teeth):
    _theta = 2.0 * math.pi * _k / _teeth
    _phi_r = _theta - _delta - _inv_alpha
    _phi_l = _theta + _delta + _inv_alpha

    # Right involute flank (from root/base to tip)
    if _has_undercut:
        # Radial extension from root to base-circle start
        _add_point(_root_radius * math.cos(_phi_r), _root_radius * math.sin(_phi_r))

    for _si in range(_samples + 1):
        _t = _t_root + (_t_tip - _t_root) * _si / _samples
        _x, _y = _rot(_ix(_t), _iy(_t), _phi_r)
        _add_point(_x, _y)

    # Tip arc
    _r_tip_ang = _phi_r + _polar(_t_tip)
    _l_tip_ang = _phi_l - _polar(_t_tip)
    _tip_steps = max(2, _samples // 4)
    for _ti in range(1, _tip_steps):
        _a = _r_tip_ang + (_l_tip_ang - _r_tip_ang) * _ti / _tip_steps
        _add_point(_outer_radius * math.cos(_a), _outer_radius * math.sin(_a))

    # Left involute flank (from tip to root/base, mirror)
    for _si in range(_samples, -1, -1):
        _t = _t_root + (_t_tip - _t_root) * _si / _samples
        _x, _y = _rot(_ix(_t), -_iy(_t), _phi_l)
        _add_point(_x, _y)

    if _has_undercut:
        _add_point(_root_radius * math.cos(_phi_l), _root_radius * math.sin(_phi_l))

    # Root arc to next tooth
    if _has_undercut:
        _arc_start = _phi_l
        _arc_end   = (_theta + 2.0 * math.pi / _teeth) - _delta - _inv_alpha
    else:
        _arc_start = _phi_l - _polar(_t_root)
        _arc_end   = (_theta + 2.0 * math.pi / _teeth) - _delta - _inv_alpha + _polar(_t_root)

    _root_steps = max(2, _samples // 2)
    for _ri in range(1, _root_steps + 1):
        _a = _arc_start + (_arc_end - _arc_start) * _ri / _root_steps
        _add_point(_root_radius * math.cos(_a), _root_radius * math.sin(_a))
"""

_PROFILE_TO_SKETCH_CODE = r"""
# Deduplicate and build sketch geometry
if (_points[0] - _points[-1]).Length > 1e-7:
    _points.append(_points[0])
_profile_indices = []
for _idx in range(len(_points) - 1):
    _p1 = _points[_idx]
    _p2 = _points[_idx + 1]
    if (_p2 - _p1).Length <= 1e-7:
        continue
    _geo = _sk.addGeometry(Part.LineSegment(_p1, _p2), False)
    _profile_indices.append(_geo)
    if len(_profile_indices) > 1:
        _sk.addConstraint(Sketcher.Constraint('Coincident', _profile_indices[-2], 2, _profile_indices[-1], 1))
if len(_profile_indices) > 1:
    _sk.addConstraint(Sketcher.Constraint('Coincident', _profile_indices[-1], 2, _profile_indices[0], 1))

# Construction circles for reference
for _label, _radius in [('RootRadius', _root_radius), ('BaseRadius', _base_radius),
                          ('PitchRadius', _pitch_radius), ('OuterRadius', _outer_radius)]:
    _ci = _sk.addGeometry(Part.Circle(FreeCAD.Vector(0,0,0), FreeCAD.Vector(0,0,1), _radius), True)
    try:
        _sk.addConstraint(Sketcher.Constraint('Radius', _ci, _radius))
        _sk.addConstraint(Sketcher.Constraint('Coincident', _ci, 3, -1, 1))
    except Exception:
        pass
"""


def _gear_header_code(
    doc_name: str,
    gear_name: str,
    body_name: str | None,
    sketch_name: str | None,
    teeth: int,
    module: float,
    width: float,
    pressure_angle: float,
    bore_diameter: float,
    clearance: float,
    backlash: float,
    samples_per_flank: int,
) -> list[str]:
    """Common preamble for all gear generators."""
    return [
        "import math, FreeCAD, Part, Sketcher",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"if not _doc: raise RuntimeError({f'Document {doc_name!r} not found'!r})",
        f"_gear_name   = {gear_name!r}",
        f"_body_name   = {body_name!r}",
        f"_sketch_name = {sketch_name!r} or (_gear_name + '_Sketch')",
        f"_teeth          = int({teeth})",
        f"_module         = float({module})",
        f"_width          = float({width})",
        f"_pressure_angle = math.radians(float({pressure_angle}))",
        f"_bore_diameter  = float({bore_diameter})",
        f"_clearance      = float({clearance})",
        f"_backlash       = float({backlash})",
        f"_samples        = max(6, int({samples_per_flank}))",
        "if _teeth < 3: raise ValueError('teeth must be >= 3')",
        "if _module <= 0: raise ValueError('module must be > 0')",
        "if _width <= 0: raise ValueError('width must be > 0')",
        "if not (0 < _pressure_angle < math.radians(45)): raise ValueError('pressure_angle must be 1-44 degrees')",
        "_pitch_radius = _module * _teeth / 2.0",
        "_base_radius  = _pitch_radius * math.cos(_pressure_angle)",
        "_outer_radius = _pitch_radius + _module",
        "_root_radius  = max(_pitch_radius - (1.25 * _module + _clearance), _module * 0.05)",
        "if _bore_diameter and _bore_diameter >= 2.0 * _root_radius:",
        "    raise ValueError('bore_diameter must be smaller than root diameter')",
        # Body
        "_body = _doc.getObject(_body_name) if _body_name else None",
        "if _body_name and not _body: raise RuntimeError('Body not found: ' + _body_name)",
        "if not _body: _body = _doc.addObject('PartDesign::Body', _gear_name + '_Body')",
        # Sketch
        "_sk = _body.newObject('Sketcher::SketchObject', _sketch_name)",
        "_origin = getattr(_body, 'Origin', None)",
        "_plane = None",
        "for _f in getattr(_origin, 'OriginFeatures', []):",
        "    if getattr(_f, 'Label', '') == 'XY_Plane': _plane = _f; break",
        "if _plane: _sk.AttachmentSupport = [(_plane,'')]; _sk.MapMode = 'FlatFace'",
        # Point collector
        "_points = []",
        "def _add_point(_x, _y):",
        "    _pt = FreeCAD.Vector(_x, _y, 0)",
        "    if not _points or (_points[-1] - _pt).Length > 1e-8:",
        "        _points.append(_pt)",
    ]


def _gear_footer_code(gear_name: str, bore_diameter: float) -> list[str]:
    lines = list(_PROFILE_TO_SKETCH_CODE.strip().splitlines())
    lines += [
        # Bore
        f"if {bore_diameter} > 0:",
        f"    _bore_idx = _sk.addGeometry(Part.Circle(FreeCAD.Vector(0,0,0),FreeCAD.Vector(0,0,1),{bore_diameter}/2.0),False)",
        f"    try:",
        f"        _sk.addConstraint(Sketcher.Constraint('Radius',_bore_idx,{bore_diameter}/2.0))",
        f"        _sk.addConstraint(Sketcher.Constraint('Coincident',_bore_idx,3,-1,1))",
        f"    except Exception: pass",
        "try: _sk.solve()",
        "except Exception: pass",
        # Pad
        *_partdesign_extrusion_helper_code(),
        *_partdesign_bool_property_helper_code(),
        f"_pad = _body.newObject('PartDesign::Pad', {gear_name!r})",
        "_pad.Profile = (_sk, [''])",
        "_pad.Length = _width",
        "_set_extrusion_symmetric(_pad, False)",
        "_sk.Visibility = False",
        "_doc.recompute()",
        "print('body_name='   + _body.Name)",
        "print('sketch_name=' + _sk.Name)",
        "print('pad_name='    + _pad.Name)",
        "print('teeth='       + str(_teeth))",
        "print('module='      + str(_module))",
        "print('pitch_dia='   + str(2.0 * _pitch_radius))",
        "print('base_dia='    + str(2.0 * _base_radius))",
        "print('outer_dia='   + str(2.0 * _outer_radius))",
        "print('root_dia='    + str(2.0 * _root_radius))",
    ]
    return lines


# ---------------------------------------------------------------------------
# P4-1  create_involute_gear  (correct mathematical profile)
# ---------------------------------------------------------------------------

def create_involute_gear_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    gear_name: str,
    teeth: int,
    module: float,
    width: float,
    pressure_angle: float = 20.0,
    bore_diameter: float = 0.0,
    clearance: float = 0.0,
    backlash: float = 0.0,
    samples_per_flank: int = 12,
    body_name: str | None = None,
    sketch_name: str | None = None,
) -> ToolResponse:
    lines = (
        _gear_header_code(doc_name, gear_name, body_name, sketch_name, teeth, module, width,
                          pressure_angle, bore_diameter, clearance, backlash, samples_per_flank)
        + list(_INVOLUTE_PROFILE_CODE.strip().splitlines())
        + _gear_footer_code(gear_name, bore_diameter)
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Involute gear '{gear_name}' created", "Failed to create involute gear")


# ---------------------------------------------------------------------------
# P4-2  create_helical_gear
# ---------------------------------------------------------------------------

def create_helical_gear_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    gear_name: str,
    teeth: int,
    module: float,
    width: float,
    helix_angle: float = 15.0,
    pressure_angle: float = 20.0,
    bore_diameter: float = 0.0,
    clearance: float = 0.0,
    backlash: float = 0.0,
    samples_per_flank: int = 12,
    body_name: str | None = None,
) -> ToolResponse:
    """
    Helical gear: generate involute profile on XY plane then use AdditiveHelix
    to twist it. The helix pitch is computed from width and helix_angle.
    """
    lines = (
        _gear_header_code(doc_name, gear_name, body_name, None, teeth, module, width,
                          pressure_angle, bore_diameter, clearance, backlash, samples_per_flank)
        + list(_INVOLUTE_PROFILE_CODE.strip().splitlines())
        + list(_PROFILE_TO_SKETCH_CODE.strip().splitlines())
        + [
            # Bore
            f"if {bore_diameter} > 0:",
            f"    _bi = _sk.addGeometry(Part.Circle(FreeCAD.Vector(0,0,0),FreeCAD.Vector(0,0,1),{bore_diameter}/2.0),False)",
            "try: _sk.solve()\nexcept Exception: pass",
            # Helix via AdditiveHelix (twist the profile)
            *_partdesign_extrusion_helper_code(),
            *_partdesign_bool_property_helper_code(),
            f"_ha = math.radians({helix_angle})",
            "_helix_pitch = _width / math.tan(_ha) if abs(math.tan(_ha)) > 1e-9 else 1e6",
            f"_hel = _body.newObject('PartDesign::AdditiveHelix', {gear_name!r})",
            "_hel.Profile = (_sk, [''])",
            "_hel.Pitch = _helix_pitch",
            "_hel.Height = _width",
            "_hel.Angle = 0",
            "_sk.Visibility = False",
            "_doc.recompute()",
            "print('body_name='     + _body.Name)",
            "print('sketch_name='   + _sk.Name)",
            "print('helix_name='    + _hel.Name)",
            "print('helix_angle='   + str({helix_angle}))",
            "print('teeth='         + str(_teeth))",
            "print('module='        + str(_module))",
            "print('pitch_dia='     + str(2.0 * _pitch_radius))",
        ]
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Helical gear '{gear_name}' created", "Failed to create helical gear")


# ---------------------------------------------------------------------------
# P4-3  compute_gear_geometry
# ---------------------------------------------------------------------------

def compute_gear_geometry_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    teeth: int,
    module: float,
    pressure_angle: float = 20.0,
    clearance: float = 0.0,
    backlash: float = 0.0,
    helix_angle: float = 0.0,
) -> ToolResponse:
    import math
    α = math.radians(pressure_angle)
    r  = module * teeth / 2.0
    r_b = r * math.cos(α)
    r_a = r + module
    r_f = max(r - 1.25 * module - clearance, module * 0.05)
    inv_α = math.tan(α) - α
    from ..responses import json_response
    return json_response({
        "teeth":          teeth,
        "module":         module,
        "pressure_angle": pressure_angle,
        "helix_angle":    helix_angle,
        "pitch_dia":      round(2 * r, 6),
        "base_dia":       round(2 * r_b, 6),
        "addendum_dia":   round(2 * r_a, 6),
        "root_dia":       round(2 * r_f, 6),
        "addendum":       round(module, 6),
        "dedendum":       round(1.25 * module + clearance, 6),
        "involute_fn":    round(inv_α, 8),
        "circular_pitch": round(math.pi * module, 6),
        "base_pitch":     round(math.pi * module * math.cos(α), 6),
    })


# ---------------------------------------------------------------------------
# P4-4  check_gear_pair
# ---------------------------------------------------------------------------

def check_gear_pair_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    teeth1: int,
    module1: float,
    teeth2: int,
    module2: float,
    pressure_angle: float = 20.0,
    center_distance: float | None = None,
) -> ToolResponse:
    import math
    from ..responses import json_response
    same_module = abs(module1 - module2) < 1e-6
    α = math.radians(pressure_angle)
    r1 = module1 * teeth1 / 2.0
    r2 = module2 * teeth2 / 2.0
    theo_cd = r1 + r2
    ratio = teeth2 / teeth1
    meshing_ok = same_module
    notes = []
    if not same_module:
        notes.append(f"Module mismatch: {module1} vs {module2} — gears will not mesh correctly")
    if center_distance is not None:
        cd_err = abs(center_distance - theo_cd)
        if cd_err > 0.01:
            notes.append(f"Center distance {center_distance:.4f} differs from theoretical {theo_cd:.4f} by {cd_err:.4f} mm")
    return json_response({
        "meshes":              meshing_ok,
        "gear_ratio":          round(ratio, 6),
        "theoretical_cd_mm":   round(theo_cd, 6),
        "center_distance_mm":  center_distance,
        "pitch_dia_1":         round(2 * r1, 6),
        "pitch_dia_2":         round(2 * r2, 6),
        "pressure_angle_deg":  pressure_angle,
        "notes":               notes,
    })
