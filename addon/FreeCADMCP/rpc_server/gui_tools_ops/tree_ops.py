"""Model-tree expand/collapse helpers (GUI thread)."""

from __future__ import annotations

from typing import Any

import FreeCAD
import FreeCADGui

from ..gui_dispatch import _flush_gui_events


def set_tree_expanded(
    doc_name: str,
    object_names: list[str] | None,
    mode: str = "expand",
) -> dict[str, Any]:
    """Expand or collapse selected model-tree items.

    Modes:
      - expand / collapse: operate on ``object_names`` (or current selection)
      - expand_document / collapse_document: whole document tree commands
    """
    doc = FreeCAD.getDocument(doc_name)
    if doc is None:
        return {"ok": False, "error": f"Document not found: {doc_name}"}

    mode_norm = str(mode or "expand").strip().lower()
    if mode_norm in ("expand_document", "collapse_document"):
        cmd = (
            "Std_TreeExpand"
            if mode_norm == "expand_document"
            else "Std_TreeCollapseDocument"
        )
        if mode_norm == "collapse_document":
            try:
                FreeCADGui.runCommand("Std_TreeCollapseDocument")
                _flush_gui_events()
                return {
                    "ok": True,
                    "mode": mode_norm,
                    "command": "Std_TreeCollapseDocument",
                }
            except Exception:
                cmd = "Std_TreeCollapse"
        FreeCADGui.runCommand(cmd)
        _flush_gui_events()
        return {"ok": True, "mode": mode_norm, "command": cmd}

    names = [str(n) for n in (object_names or []) if str(n)]
    FreeCADGui.Selection.clearSelection()
    selected: list[str] = []
    missing: list[str] = []
    for name in names:
        obj = doc.getObject(name)
        if obj is None:
            missing.append(name)
            continue
        FreeCADGui.Selection.addSelection(obj)
        selected.append(name)

    if not selected and not names:
        selected = [
            getattr(o, "Name", str(o)) for o in FreeCADGui.Selection.getSelection()
        ]

    if not selected:
        return {
            "ok": False,
            "error": "No objects to expand/collapse",
            "missing": missing,
        }

    cmd = (
        "Std_TreeExpand"
        if mode_norm in ("expand", "expanded", "open")
        else "Std_TreeCollapse"
    )
    FreeCADGui.runCommand(cmd)
    _flush_gui_events()
    return {
        "ok": True,
        "mode": "expand" if cmd == "Std_TreeExpand" else "collapse",
        "command": cmd,
        "selected": selected,
        "missing": missing,
    }


__all__ = ["set_tree_expanded"]
