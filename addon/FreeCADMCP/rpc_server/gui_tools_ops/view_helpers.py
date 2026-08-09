"""Shared active-view helpers for GUI-thread tools."""

from __future__ import annotations

import FreeCADGui


def active_view():
    gui_doc = FreeCADGui.ActiveDocument
    if gui_doc is None:
        raise RuntimeError("No active GUI document")
    view = gui_doc.activeView()
    if view is None:
        raise RuntimeError("No active 3D view")
    return view


__all__ = ["active_view"]
