"""View name normalization and active view access."""

from __future__ import annotations

import FreeCADGui

_VIEW_ALIASES = {
    "Rear": "Back",
    "Side": "Right",
    "SideRight": "Right",
    "SideLeft": "Left",
}


def normalize_view_name(view_name: str) -> str:
    name = str(view_name or "").strip()
    return _VIEW_ALIASES.get(name, name)


def active_view():
    gui_doc = FreeCADGui.ActiveDocument
    if gui_doc is None:
        raise RuntimeError("No active GUI document")
    view = gui_doc.activeView()
    if view is None:
        raise RuntimeError("No active 3D view")
    return view
