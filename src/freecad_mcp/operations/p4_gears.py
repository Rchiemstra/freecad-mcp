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
from ..template_resources import read_template_lines, render_template_lines
from .core import _run_code, _partdesign_extrusion_helper_code, _partdesign_bool_property_helper_code

logger = logging.getLogger("FreeCADMCPserver")

# ---------------------------------------------------------------------------
# Shared involute code fragment (executed inside FreeCAD via execute_code)
# ---------------------------------------------------------------------------

_INVOLUTE_PROFILE_CODE = read_template_lines("p4_gears/involute_profile.py.txt")
_PROFILE_TO_SKETCH_CODE = read_template_lines("p4_gears/profile_to_sketch.py.txt")


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
    return render_template_lines(
        "p4_gears/gear_header.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
        gear_name=repr(gear_name),
        body_name=repr(body_name),
        sketch_name=repr(sketch_name),
        teeth=repr(teeth),
        module=repr(module),
        width=repr(width),
        pressure_angle=repr(pressure_angle),
        bore_diameter=repr(bore_diameter),
        clearance=repr(clearance),
        backlash=repr(backlash),
        samples_per_flank=repr(samples_per_flank),
    )


def _gear_footer_code(gear_name: str, bore_diameter: float) -> list[str]:
    return render_template_lines(
        "p4_gears/gear_footer.py.txt",
        profile_to_sketch="\n".join(_PROFILE_TO_SKETCH_CODE),
        bore_diameter=repr(bore_diameter),
        extrusion_helpers="\n".join(_partdesign_extrusion_helper_code()),
        bool_helpers="\n".join(_partdesign_bool_property_helper_code()),
        gear_name=repr(gear_name),
    )


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
        + list(_INVOLUTE_PROFILE_CODE)
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
        + list(_INVOLUTE_PROFILE_CODE)
        + render_template_lines(
            "p4_gears/helical_footer.py.txt",
            profile_to_sketch="\n".join(_PROFILE_TO_SKETCH_CODE),
            bore_diameter=repr(bore_diameter),
            extrusion_helpers="\n".join(_partdesign_extrusion_helper_code()),
            bool_helpers="\n".join(_partdesign_bool_property_helper_code()),
            helix_angle=repr(helix_angle),
            gear_name=repr(gear_name),
        )
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
