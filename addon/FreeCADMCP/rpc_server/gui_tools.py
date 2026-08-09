"""GUI-thread helpers for tree, selection, section clip, and document focus."""

from __future__ import annotations

from typing import Any

import FreeCAD
import FreeCADGui

from .gui_dispatch import _flush_gui_events


_VIEW_ALIASES = {
    "Rear": "Back",
    "Side": "Right",
    "SideRight": "Right",
    "SideLeft": "Left",
}


def normalize_view_name(view_name: str) -> str:
    name = str(view_name or "").strip()
    return _VIEW_ALIASES.get(name, name)


def _active_view():
    gui_doc = FreeCADGui.ActiveDocument
    if gui_doc is None:
        raise RuntimeError("No active GUI document")
    view = gui_doc.activeView()
    if view is None:
        raise RuntimeError("No active 3D view")
    return view


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
        # Prefer document-level collapse command when available.
        if mode_norm == "collapse_document":
            try:
                FreeCADGui.runCommand("Std_TreeCollapseDocument")
                _flush_gui_events()
                return {"ok": True, "mode": mode_norm, "command": "Std_TreeCollapseDocument"}
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
        # Operate on whatever is already selected.
        selected = [
            getattr(o, "Name", str(o))
            for o in FreeCADGui.Selection.getSelection()
        ]

    if not selected:
        return {
            "ok": False,
            "error": "No objects to expand/collapse",
            "missing": missing,
        }

    cmd = "Std_TreeExpand" if mode_norm in ("expand", "expanded", "open") else "Std_TreeCollapse"
    FreeCADGui.runCommand(cmd)
    _flush_gui_events()
    return {
        "ok": True,
        "mode": "expand" if cmd == "Std_TreeExpand" else "collapse",
        "command": cmd,
        "selected": selected,
        "missing": missing,
    }


def select_subshapes(
    doc_name: str,
    selections: list[dict[str, Any]] | list[str],
    clear: bool = True,
) -> dict[str, Any]:
    """Select whole objects or sub-shapes (``FaceN`` / ``EdgeN`` / ``VertexN``).

    ``selections`` entries may be:
      - ``"Box"`` or ``"Box:Face1"``
      - ``{"object": "Box", "sub": "Face1"}`` / ``{"obj": ..., "subshape": ...}``
    """
    doc = FreeCAD.getDocument(doc_name)
    if doc is None:
        return {"ok": False, "error": f"Document not found: {doc_name}"}

    if clear:
        FreeCADGui.Selection.clearSelection()

    selected: list[dict[str, str]] = []
    errors: list[str] = []

    for item in selections or []:
        obj_name = ""
        sub = ""
        if isinstance(item, str):
            if ":" in item:
                obj_name, sub = item.split(":", 1)
            else:
                obj_name, sub = item, ""
        elif isinstance(item, dict):
            obj_name = str(
                item.get("object")
                or item.get("obj")
                or item.get("name")
                or ""
            )
            sub = str(
                item.get("sub")
                or item.get("subshape")
                or item.get("subName")
                or ""
            )
        else:
            errors.append(f"Unsupported selection entry: {item!r}")
            continue

        obj_name = obj_name.strip()
        sub = sub.strip()
        if not obj_name:
            errors.append(f"Missing object name in {item!r}")
            continue
        obj = doc.getObject(obj_name)
        if obj is None:
            errors.append(f"Object not found: {obj_name}")
            continue
        try:
            if sub:
                FreeCADGui.Selection.addSelection(doc.Name, obj.Name, sub)
            else:
                FreeCADGui.Selection.addSelection(obj)
            selected.append({"object": obj.Name, "sub": sub})
        except Exception as exc:
            errors.append(f"{obj_name}:{sub or '<obj>'}: {exc}")

    _flush_gui_events()
    return {
        "ok": not errors or bool(selected),
        "selected": selected,
        "errors": errors,
        "count": len(selected),
    }


def get_selection() -> dict[str, Any]:
    items = []
    for sel in FreeCADGui.Selection.getSelectionEx():
        for sub in sel.SubElementNames or [""]:
            items.append(
                {
                    "document": sel.DocumentName,
                    "object": sel.ObjectName,
                    "sub": sub,
                }
            )
    return {"ok": True, "selection": items, "count": len(items)}


def set_section_view(
    enabled: bool | None = None,
    *,
    placement: dict[str, Any] | None = None,
    base: list[float] | tuple[float, ...] | None = None,
    normal: list[float] | tuple[float, ...] | None = None,
    no_manip: bool = True,
) -> dict[str, Any]:
    """Enable/disable/query the active view clipping (section) plane."""
    view = _active_view()
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
            try:
                pla.Rotation = FreeCAD.Rotation(rot)
            except Exception:
                pass
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
    has_after = bool(view.hasClippingPlane()) if hasattr(view, "hasClippingPlane") else bool(enabled)
    return {
        "ok": True,
        "enabled": has_after,
        "requested_enabled": enabled,
        "placement_base": [pla.Base.x, pla.Base.y, pla.Base.z],
    }


def open_document(path: str) -> dict[str, Any]:
    path = str(path)
    if not path:
        return {"ok": False, "error": "path is required"}
    doc = FreeCAD.openDocument(path)
    if doc is None:
        return {"ok": False, "error": f"Failed to open: {path}"}
    try:
        FreeCAD.setActiveDocument(doc.Name)
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(doc.Name)
    except Exception:
        pass
    _flush_gui_events()
    return {"ok": True, "document": doc.Name, "label": doc.Label, "path": path}


def activate_document(doc_name: str) -> dict[str, Any]:
    doc = FreeCAD.getDocument(doc_name)
    if doc is None:
        return {"ok": False, "error": f"Document not found: {doc_name}"}
    FreeCAD.setActiveDocument(doc.Name)
    try:
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(doc.Name)
    except Exception as exc:
        return {"ok": False, "error": f"Activated App doc but GUI failed: {exc}"}
    _flush_gui_events()
    return {"ok": True, "document": doc.Name, "label": doc.Label}


def get_gui_state() -> dict[str, Any]:
    """Read-only snapshot of the active GUI context.

    Reports the active document, active PartDesign Body, active workbench, the
    object currently in edit-mode, and the current selection. Every probe is
    guarded so a headless or partially-initialised GUI degrades to ``None``
    rather than raising.
    """
    state: dict[str, Any] = {"ok": True}

    try:
        app_doc = FreeCAD.ActiveDocument
        state["active_document"] = app_doc.Name if app_doc else None
        state["active_document_label"] = app_doc.Label if app_doc else None
    except Exception as exc:
        state["active_document"] = None
        state["active_document_error"] = str(exc)

    try:
        wb = FreeCADGui.activeWorkbench()
        state["active_workbench"] = (
            wb.name() if hasattr(wb, "name") else type(wb).__name__
        )
    except Exception as exc:
        state["active_workbench"] = None
        state["active_workbench_error"] = str(exc)

    try:
        gui_doc = FreeCADGui.ActiveDocument
        if gui_doc is not None:
            in_edit = gui_doc.getInEdit()
            edit_obj = getattr(in_edit, "Object", None) if in_edit is not None else None
            state["edit_mode_object"] = getattr(edit_obj, "Name", None)
            try:
                view = gui_doc.activeView()
            except Exception:
                view = None
            active_body = None
            if view is not None and hasattr(view, "getActiveObject"):
                active_body = view.getActiveObject("pdbody")
            state["active_body"] = getattr(active_body, "Name", None)
        else:
            state["edit_mode_object"] = None
            state["active_body"] = None
    except Exception as exc:
        state["active_body"] = None
        state["edit_mode_object"] = None
        state["edit_mode_error"] = str(exc)

    try:
        sel = get_selection()
        state["selection"] = sel.get("selection", [])
        state["selection_count"] = sel.get("count", 0)
    except Exception as exc:
        state["selection"] = []
        state["selection_error"] = str(exc)

    return state


def recompute_and_wait(doc_name: str) -> dict[str, Any]:
    """Recompute a document and block until the GUI is idle again.

    Runs ``doc.recompute()`` on the GUI thread, drains the queued Qt events so
    the tree/3D view reflect the result, then reports per-object recompute state.
    An explicit recompute-complete + GUI-idle barrier: after this returns a
    follow-up model check sees a settled document, complementing the
    ``check_rpc_sync`` nonce probe (which only proves the queue is live).
    """
    doc = FreeCAD.getDocument(doc_name)
    if doc is None:
        return {"ok": False, "error": f"Document not found: {doc_name}"}

    touched = doc.recompute()
    _flush_gui_events()

    objects: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    pending: list[str] = []
    for obj in doc.Objects:
        st = list(getattr(obj, "State", []))
        try:
            valid = bool(obj.isValid())
        except Exception:
            valid = True
        entry = {"name": obj.Name, "state": st, "valid": valid}
        objects.append(entry)
        if (not valid) or any(s in ("Invalid", "Error", "Erroneous") for s in st):
            errors.append(entry)
        if "Touched" in st:
            pending.append(obj.Name)

    return {
        "ok": not errors,
        "document": doc.Name,
        "recomputed_count": int(touched) if isinstance(touched, int) else None,
        "objects": objects,
        "errors": errors,
        "pending_recompute": pending,
        "settled": not pending,
        "idle": True,
    }
