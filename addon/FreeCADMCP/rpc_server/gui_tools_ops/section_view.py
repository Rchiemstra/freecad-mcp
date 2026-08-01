"""Section view (clipping plane) operations."""

from __future__ import annotations

import contextlib
from typing import Any

import FreeCAD

from ..gui_dispatch import _flush_gui_events
from .view_aliases import active_view


def set_section_view(
    enabled: bool | None = None,
    *,
    placement: dict[str, Any] | None = None,
    base: list[float] | tuple[float, ...] | None = None,
    normal: list[float] | tuple[float, ...] | None = None,
    no_manip: bool = True,
) -> dict[str, Any]:
    """Enable/disable/query the active view clipping (section) plane."""
    view = active_view()
    has = bool(view.hasClippingPlane()) if hasattr(view, "hasClippingPlane") else False

    if enabled is None and placement is None and base is None and normal is None:
        return {"ok": True, "enabled": has}

    pla = FreeCAD.Placement()
    if placement:
        base_v = placement.get("base") or placement.get("Base") or [0, 0, 0]
        pla.Base = FreeCAD.Vector(*[float(x) for x in base_v])
        rot = placement.get("rotation") or placement.get("Rotation")
        if isinstance(rot, dict) and "axis" in rot:
            axis = FreeCAD.Vector(*[float(x) for x in rot["axis"]])
            angle = float(rot.get("angle", rot.get("angle_deg", 0)))
            pla.Rotation = FreeCAD.Rotation(axis, angle)
        elif rot is not None:
            with contextlib.suppress(Exception):
                pla.Rotation = FreeCAD.Rotation(rot)
    elif base is not None or normal is not None:
        b = FreeCAD.Vector(*(float(x) for x in (base or (0, 0, 0))))
        n = FreeCAD.Vector(*(float(x) for x in (normal or (0, 0, 1))))
        pla.Base = b
        if n.Length > 1e-12:
            pla.Rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), n)

    toggle = -1
    if enabled is True:
        toggle = 1
    elif enabled is False:
        toggle = 0

    try:
        view.toggleClippingPlane(
            toggle=toggle,
            beforeEditing=False,
            noManip=bool(no_manip),
            pla=pla,
        )
    except TypeError:
        # Older signatures may be positional-only.
        view.toggleClippingPlane(toggle, False, bool(no_manip), pla)

    _flush_gui_events()
    has_after = (
        bool(view.hasClippingPlane())
        if hasattr(view, "hasClippingPlane")
        else bool(enabled)
    )
    return {
        "ok": True,
        "enabled": has_after,
        "requested_enabled": enabled,
        "placement_base": [pla.Base.x, pla.Base.y, pla.Base.z],
    }
