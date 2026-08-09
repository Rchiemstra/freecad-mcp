"""Named view orientation dispatch tables."""

from __future__ import annotations

from typing import Any

import FreeCAD
import FreeCADGui

VIEW_DISPATCH = {
    "Isometric": "viewIsometric",
    "Front": "viewFront",
    "Top": "viewTop",
    "Right": "viewRight",
    "Back": "viewBack",
    "Left": "viewLeft",
    "Bottom": "viewBottom",
    "Dimetric": "viewDimetric",
    "Trimetric": "viewTrimetric",
}

STD_COMMAND_DISPATCH = {
    "Isometric": "Std_ViewIsometric",
    "Front": "Std_ViewFront",
    "Top": "Std_ViewTop",
    "Right": "Std_ViewRight",
    "Back": "Std_ViewRear",
    "Left": "Std_ViewLeft",
    "Bottom": "Std_ViewBottom",
    "Dimetric": "Std_ViewDimetric",
    "Trimetric": "Std_ViewTrimetric",
}

VIEW_ALIASES = {
    "Rear": "Back",
    "Side": "Right",
    "SideRight": "Right",
    "SideLeft": "Left",
}


def apply_view_orientation(view: Any, view_name: str) -> None:
    view_name = VIEW_ALIASES.get(str(view_name), str(view_name))
    method_name = VIEW_DISPATCH.get(view_name)
    if method_name is None:
        raise ValueError(f"Invalid view name: {view_name}")
    if hasattr(view, method_name):
        getattr(view, method_name)()
        return
    cmd = STD_COMMAND_DISPATCH.get(view_name)
    if cmd:
        FreeCADGui.runCommand(cmd)
        return
    FreeCAD.Console.PrintWarning(
        f"apply_view_orientation: no method or command for '{view_name}'\n"
    )
