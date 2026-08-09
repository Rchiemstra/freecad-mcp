"""Actor-scoped tree, selection, section, and GUI-state RPC methods."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .collaboration_context import (
    public_error,
    snapshot_personal_view,
    update_personal_view,
)
from .collaboration_context_core import request_actor, resolve_document
from .collaboration_context_dispatch import dispatch_gui


def _selection_entry(item: Any) -> tuple[str, str, str | None]:
    if isinstance(item, str):
        text = item.strip()
        if ":" in text:
            obj, sub = text.split(":", 1)
            return obj.strip(), sub.strip(), None
        if "." in text:
            obj, sub = text.split(".", 1)
            return obj.strip(), sub.strip(), None
        return text, "", None
    if isinstance(item, Mapping):
        obj = str(
            item.get("object") or item.get("obj") or item.get("name") or ""
        ).strip()
        sub = str(
            item.get("sub") or item.get("subshape") or item.get("subName") or ""
        ).strip()
        return obj, sub, None
    return "", "", f"Unsupported selection entry: {item!r}"


def _selection_items(document: Any, paths: list[str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for path in paths:
        obj, _, sub = path.partition(".")
        items.append(
            {
                "document": str(document.Name),
                "object": obj,
                "sub": sub,
            }
        )
    return items


def activate_document(self, doc_name: str) -> dict[str, Any]:
    """Select the actor's document without changing the human active document."""

    try:
        document, _, _ = update_personal_view(
            self, doc_name, lambda _document, _context: None
        )
        return {
            "ok": True,
            "document": str(document.Name),
            "label": str(getattr(document, "Label", document.Name)),
        }
    except Exception as exc:
        return public_error(self, exc)


def set_tree_expanded(
    self,
    doc_name: str,
    object_names: list | None = None,
    mode: str = "expand",
) -> dict[str, Any]:
    """Update the actor's copied tree state, never the global tree selection."""

    mode_norm = str(mode or "expand").strip().lower()
    try:

        def update(document, context):
            expanded = list(context["expanded_tree_paths"])
            requested = [str(name) for name in (object_names or []) if str(name)]
            if not requested and mode_norm not in {
                "expand_document",
                "collapse_document",
            }:
                requested = [
                    path.partition(".")[0] for path in context["selection_paths"]
                ]
            missing = [name for name in requested if document.getObject(name) is None]
            names = [name for name in requested if name not in missing]
            if mode_norm == "expand_document":
                names = [str(obj.Name) for obj in getattr(document, "Objects", ())]
                expanded = list(dict.fromkeys(names))
            elif mode_norm == "collapse_document":
                expanded = []
            elif mode_norm in {"expand", "expanded", "open"}:
                expanded = list(dict.fromkeys([*expanded, *names]))
            else:
                remove = set(names)
                expanded = [name for name in expanded if name not in remove]
            context["expanded_tree_paths"] = expanded
            return names, missing

        _, _, (selected, missing) = update_personal_view(self, doc_name, update)
        if mode_norm in {"expand_document", "collapse_document"}:
            command = (
                "Std_TreeExpand"
                if mode_norm == "expand_document"
                else "Std_TreeCollapseDocument"
            )
            return {"ok": True, "mode": mode_norm, "command": command}
        if not selected and mode_norm not in {
            "expand_document",
            "collapse_document",
        }:
            return {
                "ok": False,
                "error": "No objects to expand/collapse",
                "missing": missing,
            }
        command = (
            "Std_TreeExpand"
            if mode_norm in {"expand", "expanded", "open", "expand_document"}
            else "Std_TreeCollapse"
        )
        return {
            "ok": True,
            "mode": "expand" if command == "Std_TreeExpand" else "collapse",
            "command": command,
            "selected": selected,
            "missing": missing,
        }
    except Exception as exc:
        return public_error(self, exc)


def select_subshapes(
    self,
    doc_name: str,
    selections: list | None = None,
    clear: bool = True,
) -> dict[str, Any]:
    """Persist only this actor's object/subshape selection paths."""

    try:

        def update(document, context):
            paths = [] if clear else list(context["selection_paths"])
            selected: list[dict[str, str]] = []
            errors: list[str] = []
            for item in selections or []:
                obj_name, sub, error = _selection_entry(item)
                if error:
                    errors.append(error)
                    continue
                obj = document.getObject(obj_name) if obj_name else None
                if obj is None:
                    errors.append(f"Object not found: {obj_name}")
                    continue
                get_subobject = getattr(obj, "getSubObject", None)
                if sub and callable(get_subobject) and get_subobject(sub) is None:
                    errors.append(f"Subobject not found: {obj_name}.{sub}")
                    continue
                path = f"{obj_name}.{sub}" if sub else obj_name
                if path not in paths:
                    paths.append(path)
                selected.append({"object": str(obj.Name), "sub": sub})
            context["selection_paths"] = paths
            return selected, errors

        _, _, (selected, errors) = update_personal_view(self, doc_name, update)
        return {
            "ok": not errors or bool(selected),
            "selected": selected,
            "errors": errors,
            "count": len(selected),
        }
    except Exception as exc:
        return public_error(self, exc)


def get_selection(self) -> dict[str, Any]:
    try:
        document, context = snapshot_personal_view(self)
        items = _selection_items(document, context["selection_paths"])
        return {"ok": True, "selection": items, "count": len(items)}
    except Exception as exc:
        return public_error(self, exc)


def get_gui_state(self) -> dict[str, Any]:
    try:
        document, context = snapshot_personal_view(self)
        selection = _selection_items(document, context["selection_paths"])
        actor = request_actor(self)
        metadata = self._gui_collaborators.personal_view_registry.metadata(
            actor, str(document.Name)
        )
        return {
            "ok": True,
            "active_document": str(document.Name),
            "active_document_label": str(getattr(document, "Label", document.Name)),
            "active_workbench": context["active_workbench"] or None,
            "edit_mode_object": context["edit_focus"] or None,
            "active_body": metadata.get("active_body") or None,
            "selection": selection,
            "selection_count": len(selection),
        }
    except Exception as exc:
        return public_error(self, exc)


def get_report_view(
    self,
    max_lines: int | None = 200,
    clear: bool = False,
) -> dict[str, Any]:
    """Read FreeCAD Report view text (application-global Console dock)."""

    from ...gui_tools_ops.report_view import get_report_view as read_report_view

    try:
        res = dispatch_gui(
            self,
            lambda: read_report_view(max_lines=max_lines, clear=clear),
        )
    except Exception as exc:
        return public_error(self, exc)
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": str(res)}


def set_section_view(
    self,
    enabled: bool | None = None,
    placement: dict | None = None,
    base: list | None = None,
    normal: list | None = None,
    no_manip: bool = True,
) -> dict[str, Any]:
    """Apply shared presentation to the actor's explicit document target."""

    collaborators = self._gui_collaborators
    try:
        actor = request_actor(self)

        def apply_section():
            document = resolve_document(self, actor)
            return collaborators.set_section_view(
                str(document.Name),
                enabled,
                placement=placement,
                base=base,
                normal=normal,
                no_manip=no_manip,
            )

        res = dispatch_gui(
            self,
            apply_section,
        )
    except Exception as exc:
        return public_error(self, exc)
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": str(res)}


__all__ = [
    "activate_document",
    "get_gui_state",
    "get_report_view",
    "get_selection",
    "select_subshapes",
    "set_section_view",
    "set_tree_expanded",
]
