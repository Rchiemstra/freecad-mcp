"""Named-document section-view presentation adapter."""

from __future__ import annotations

import contextlib
from typing import Any


def _named_view(gui_module, document_name):
    gui_document = gui_module.getDocument(str(document_name))
    if gui_document is None:
        raise RuntimeError(f"GUI document not found: {document_name}")
    view = gui_document.activeView()
    if view is None:
        raise RuntimeError(f"No 3D view for document: {document_name}")
    return view


def set_section_view(
    freecad,
    gui_module,
    flush_gui_events,
    document_name: str,
    enabled: bool | None = None,
    *,
    placement: dict[str, Any] | None = None,
    base: list[float] | tuple[float, ...] | None = None,
    normal: list[float] | tuple[float, ...] | None = None,
    no_manip: bool = True,
) -> dict[str, Any]:
    """Mutate only the explicitly resolved document's shared presentation."""

    view = _named_view(gui_module, document_name)
    has = bool(view.hasClippingPlane()) if hasattr(view, "hasClippingPlane") else False
    if enabled is None and placement is None and base is None and normal is None:
        return {"ok": True, "enabled": has, "document": str(document_name)}

    plane = freecad.Placement()
    if placement:
        base_value = placement.get("base") or placement.get("Base") or [0, 0, 0]
        plane.Base = freecad.Vector(*[float(value) for value in base_value])
        rotation = placement.get("rotation") or placement.get("Rotation")
        if isinstance(rotation, dict) and "axis" in rotation:
            axis = freecad.Vector(*[float(value) for value in rotation["axis"]])
            angle = float(rotation.get("angle", rotation.get("angle_deg", 0)))
            plane.Rotation = freecad.Rotation(axis, angle)
        elif rotation is not None:
            with contextlib.suppress(Exception):
                plane.Rotation = freecad.Rotation(rotation)
    elif base is not None or normal is not None:
        plane.Base = freecad.Vector(*(float(value) for value in (base or (0, 0, 0))))
        direction = freecad.Vector(*(float(value) for value in (normal or (0, 0, 1))))
        if direction.Length > 1e-12:
            plane.Rotation = freecad.Rotation(freecad.Vector(0, 0, 1), direction)

    toggle = 1 if enabled is True else 0 if enabled is False else -1
    try:
        view.toggleClippingPlane(
            toggle=toggle,
            beforeEditing=False,
            noManip=bool(no_manip),
            pla=plane,
        )
    except TypeError:
        view.toggleClippingPlane(toggle, False, bool(no_manip), plane)
    flush_gui_events()
    enabled_after = (
        bool(view.hasClippingPlane())
        if hasattr(view, "hasClippingPlane")
        else bool(enabled)
    )
    return {
        "ok": True,
        "enabled": enabled_after,
        "requested_enabled": enabled,
        "document": str(document_name),
        "placement_base": [plane.Base.x, plane.Base.y, plane.Base.z],
    }


__all__ = ["set_section_view"]
