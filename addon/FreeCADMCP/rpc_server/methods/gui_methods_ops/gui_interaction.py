"""Tree, selection, section, and GUI-state RPC methods (Phase 4 slice 4G)."""

from __future__ import annotations

from typing import Any


def activate_document(self, doc_name: str) -> dict[str, Any]:
    from ...gui_tools import activate_document as _activate_document

    res = self._dispatch_gui(lambda: _activate_document(doc_name))
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": str(res)}


def set_tree_expanded(
    self,
    doc_name: str,
    object_names: list | None = None,
    mode: str = "expand",
) -> dict[str, Any]:
    from ...gui_tools import set_tree_expanded as _set_tree_expanded

    res = self._dispatch_gui(
        lambda: _set_tree_expanded(doc_name, object_names, mode)
    )
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": str(res)}


def select_subshapes(
    self,
    doc_name: str,
    selections: list | None = None,
    clear: bool = True,
) -> dict[str, Any]:
    from ...gui_tools import select_subshapes as _select_subshapes

    res = self._dispatch_gui(
        lambda: _select_subshapes(doc_name, selections or [], clear)
    )
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": str(res)}


def get_selection(self) -> dict[str, Any]:
    from ...gui_tools import get_selection as _get_selection

    res = self._dispatch_gui(_get_selection)
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": str(res)}


def get_gui_state(self) -> dict[str, Any]:
    from ...gui_tools import get_gui_state as _get_gui_state

    res = self._dispatch_gui(_get_gui_state)
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
    from ...gui_tools import set_section_view as _set_section_view

    res = self._dispatch_gui(
        lambda: _set_section_view(
            enabled,
            placement=placement,
            base=base,
            normal=normal,
            no_manip=no_manip,
        )
    )
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": str(res)}


__all__ = [
    "activate_document",
    "get_gui_state",
    "get_selection",
    "select_subshapes",
    "set_section_view",
    "set_tree_expanded",
]
