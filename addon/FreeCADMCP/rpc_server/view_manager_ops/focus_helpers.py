"""Focus-object normalization and camera framing helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import FreeCAD
import FreeCADGui


def normalize_focus_names(
    focus_object: str | None = None,
    focus_objects: Sequence[str] | None = None,
) -> list[str]:
    names: list[str] = []
    if focus_objects:
        names.extend(str(name) for name in focus_objects if str(name))
    if focus_object:
        for part in str(focus_object).split(","):
            part = part.strip()
            if part and part not in names:
                names.append(part)
    return names


def resolve_focus_targets(names: Sequence[str]) -> list[Any]:
    doc = FreeCAD.ActiveDocument
    if not doc:
        return []
    targets = []
    for name in names:
        obj = doc.getObject(name)
        if obj is not None:
            targets.append(obj)
    return targets


def frame_on_targets(view: Any, targets: Sequence[Any]) -> bool:
    """Select targets and frame the view. Returns True when a selection was used."""
    if not targets:
        view.fitAll()
        return False
    FreeCADGui.Selection.clearSelection()
    for obj in targets:
        FreeCADGui.Selection.addSelection(obj)
    FreeCADGui.SendMsgToActiveView("ViewSelection")
    return True


def apply_yaw(view: Any, yaw_deg: float | None) -> None:
    if yaw_deg is None:
        return
    try:
        if hasattr(view, "setCameraOrientation"):
            current = view.getCameraOrientation()
            extra = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), float(yaw_deg))
            view.setCameraOrientation((extra * FreeCAD.Rotation(*current)).Q)
        elif hasattr(view, "viewRotateLeft"):
            steps = round(float(yaw_deg) / 10.0) % 36
            for _ in range(max(0, steps)):
                view.viewRotateLeft()
    except Exception as exc:
        FreeCAD.Console.PrintWarning(f"view yaw apply failed: {exc}\n")
