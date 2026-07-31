"""Placement / Rotation JSON codec with an explicit public angle-unit contract.

Public MCP Placement/Rotation JSON uses degrees for ``Rotation.Angle`` and for
Yaw/Pitch/Roll. This matches FreeCAD's documented Python constructors:

* ``FreeCAD.Rotation(axis, angle)`` interprets *angle* as degrees
  (``RotationPy::PyInit`` converts with ``toRadians``).
* ``rotation.Angle`` returns radians (``RotationPy::getAngle`` reads the
  internal radian ``_angle``).
* Yaw/Pitch/Roll getters/setters already use degrees.

Serialize converts radians → degrees; deserialize passes degrees into the
axis-angle constructor. ``get_object`` / ``edit_object`` therefore round-trip.
"""

from __future__ import annotations

import math
from typing import Any

import FreeCAD

# Tolerance for degree round-trips through FreeCAD's radian storage.
ANGLE_DEG_TOL = 1e-9


def degrees_from_freecad_angle(angle_rad: Any) -> float:
    """Convert FreeCAD ``Rotation.Angle`` (radians) to public degrees."""
    return float(angle_rad) * (180.0 / math.pi)


def freecad_angle_from_degrees(angle_deg: Any) -> float:
    """Convert public degrees to FreeCAD's internal radian storage unit.

    Only used by FreeCAD-semantic test doubles; real FreeCAD constructors take
    degrees and convert internally.
    """
    return float(angle_deg) * (math.pi / 180.0)


def _as_vector(
    val: Any, *, default: tuple[float, float, float] = (0.0, 0.0, 0.0)
) -> Any:
    """Build a ``FreeCAD.Vector`` from a dict, sequence, or existing Vector."""
    if isinstance(val, FreeCAD.Vector):
        return val
    if isinstance(val, dict):
        return FreeCAD.Vector(
            float(val.get("x", default[0])),
            float(val.get("y", default[1])),
            float(val.get("z", default[2])),
        )
    if isinstance(val, (list, tuple)) and len(val) >= 3:
        return FreeCAD.Vector(float(val[0]), float(val[1]), float(val[2]))
    if val is None:
        return FreeCAD.Vector(*default)
    raise TypeError(f"Expected Vector-like value, got {val!r}.")


def vector_to_dict(value: Any) -> dict[str, float]:
    return {"x": float(value.x), "y": float(value.y), "z": float(value.z)}


def rotation_to_dict(value: Any) -> dict[str, Any]:
    """Serialize ``FreeCAD.Rotation`` to public JSON (Angle in degrees)."""
    return {
        "Axis": vector_to_dict(value.Axis),
        "Angle": degrees_from_freecad_angle(value.Angle),
    }


def placement_to_dict(value: Any) -> dict[str, Any]:
    """Serialize ``FreeCAD.Placement`` to public JSON (Angle in degrees)."""
    return {
        "Base": vector_to_dict(value.Base),
        "Rotation": rotation_to_dict(value.Rotation),
    }


def dict_to_rotation(val: Any) -> Any:
    """Build ``FreeCAD.Rotation`` from public JSON (Angle / YPR in degrees)."""
    if isinstance(val, FreeCAD.Rotation):
        return val
    if not isinstance(val, dict):
        raise TypeError(
            f"Rotation value must be a dict or FreeCAD.Rotation, got {val!r}."
        )
    if any(k in val for k in ("Yaw", "Pitch", "Roll")):
        return FreeCAD.Rotation(
            float(val.get("Yaw", 0)),
            float(val.get("Pitch", 0)),
            float(val.get("Roll", 0)),
        )
    axis = val.get("Axis", {})
    # Public contract: Angle is degrees, matching FreeCAD.Rotation(axis, deg).
    return FreeCAD.Rotation(
        _as_vector(axis, default=(0.0, 0.0, 1.0)),
        float(val.get("Angle", 0)),
    )


def dict_to_placement(val: Any) -> Any:
    """Convert a JSON-friendly placement dict into ``FreeCAD.Placement``.

    Public form (Angle in **degrees**)::

        {"Base": {"x": 0, "y": 0, "z": 10},
         "Rotation": {"Axis": {"x": 0, "y": 0, "z": 1}, "Angle": 90}}

    Also accepts ``Position`` as an alias for ``Base``, a bare Base/Position
    dict (identity rotation), and Yaw/Pitch/Roll rotation components (degrees).
    """
    if isinstance(val, FreeCAD.Placement):
        return val
    if not isinstance(val, dict):
        raise TypeError(
            f"Placement value must be a dict or FreeCAD.Placement, got {val!r}."
        )

    if "Base" in val:
        pos = val["Base"]
    elif "Position" in val:
        pos = val["Position"]
    else:
        pos = {}
    base = _as_vector(pos)

    rot = val.get("Rotation", {})
    if isinstance(rot, FreeCAD.Rotation):
        rotation = rot
    elif isinstance(rot, dict):
        rotation = dict_to_rotation(rot)
    elif rot in (None, {}):
        rotation = FreeCAD.Rotation()
    else:
        raise TypeError(f"Rotation value must be a dict or FreeCAD.Rotation, got {rot!r}.")

    return FreeCAD.Placement(base, rotation)
