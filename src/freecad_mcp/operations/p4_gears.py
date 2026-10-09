"""
P4 — Gear library.

create_involute_gear uses the correct mathematical involute parametrization.
"""
from __future__ import annotations

import math

from ..freecad_client import FreeCADConnection
from ..responses.constants import ToolResponse
from .parametric_ops.create_helical_gear import create_helical_gear_operation
from .parametric_ops.create_involute_gear import create_involute_gear_operation


def _gear_input_error(
    *,
    teeth: object,
    module: object,
    suffix: str = "",
    pressure_angle: float = 20.0,
    clearance: float = 0.0,
    backlash: float = 0.0,
    helix_angle: float = 0.0,
) -> str | None:
    """Mirror create_involute_gear's limits; NaN fails every comparison."""

    if isinstance(teeth, bool) or not isinstance(teeth, int) or teeth < 3:
        return f"teeth{suffix} must be >= 3"
    if not (isinstance(module, int | float) and math.isfinite(module) and module > 0):
        return f"module{suffix} must be > 0"
    if not 0 < pressure_angle < 45:
        return "pressure_angle must be 1-44 degrees"
    if not clearance >= 0:
        return "clearance must be >= 0"
    if not backlash >= 0:
        return "backlash must be >= 0"
    if not -90 < helix_angle < 90:
        return "helix_angle must be between -90 and 90 degrees"
    return None


def _invalid_argument(message: str) -> ToolResponse:
    from ..responses.tool_results import tool_fail

    return tool_fail(message, error_code="INVALID_ARGUMENT")


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
    from ..responses.tool_results import json_response

    error = _gear_input_error(
        teeth=teeth,
        module=module,
        pressure_angle=pressure_angle,
        clearance=clearance,
        backlash=backlash,
        helix_angle=helix_angle,
    )
    if error is not None:
        return _invalid_argument(error)
    alpha = math.radians(pressure_angle)
    r = module * teeth / 2.0
    r_b = r * math.cos(alpha)
    r_a = r + module
    r_f = max(r - 1.25 * module - clearance, module * 0.05)
    inv_alpha = math.tan(alpha) - alpha
    return json_response(
        {
            "teeth": teeth,
            "module": module,
            "pressure_angle": pressure_angle,
            "helix_angle": helix_angle,
            "pitch_dia": round(2 * r, 6),
            "base_dia": round(2 * r_b, 6),
            "addendum_dia": round(2 * r_a, 6),
            "root_dia": round(2 * r_f, 6),
            "addendum": round(module, 6),
            "dedendum": round(1.25 * module + clearance, 6),
            "involute_fn": round(inv_alpha, 8),
            "circular_pitch": round(math.pi * module, 6),
            "base_pitch": round(math.pi * module * math.cos(alpha), 6),
        }
    )


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
    from ..responses.tool_results import json_response

    error = _gear_input_error(
        teeth=teeth1, module=module1, suffix="1", pressure_angle=pressure_angle
    ) or _gear_input_error(teeth=teeth2, module=module2, suffix="2")
    if error is None and center_distance is not None and not center_distance > 0:
        error = "center_distance must be > 0"
    if error is not None:
        return _invalid_argument(error)
    same_module = abs(module1 - module2) < 1e-6
    r1 = module1 * teeth1 / 2.0
    r2 = module2 * teeth2 / 2.0
    theo_cd = r1 + r2
    ratio = teeth2 / teeth1
    notes: list[str] = []
    if not same_module:
        notes.append(f"Module mismatch: {module1} vs {module2} — gears will not mesh correctly")
    if center_distance is not None:
        cd_err = abs(center_distance - theo_cd)
        if cd_err > 0.01:
            notes.append(
                f"Center distance {center_distance:.4f} differs from "
                f"theoretical {theo_cd:.4f} by {cd_err:.4f} mm"
            )
    return json_response(
        {
            "meshes": same_module,
            "gear_ratio": round(ratio, 6),
            "theoretical_cd_mm": round(theo_cd, 6),
            "center_distance_mm": center_distance,
            "pitch_dia_1": round(2 * r1, 6),
            "pitch_dia_2": round(2 * r2, 6),
            "pressure_angle_deg": pressure_angle,
            "notes": notes,
        }
    )


__all__ = [
    "check_gear_pair_operation",
    "compute_gear_geometry_operation",
    "create_helical_gear_operation",
    "create_involute_gear_operation",
]
