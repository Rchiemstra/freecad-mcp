"""Interactive GUI operations: tree, selection, section, multi-document compare."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse, json_response, tool_fail, tool_ok
from ..template_resources import render_template_text
from .diagnostics import _diff_states, _response_text
from .p7_assembly import _doc_preamble, _run_json_code


logger = logging.getLogger("FreeCADMCPserver")

_VIEW_ALIASES = {
    "Rear": "Back",
    "Side": "Right",
    "SideRight": "Right",
    "SideLeft": "Left",
}


def normalize_view_name(view_name: str) -> str:
    name = str(view_name or "").strip()
    return _VIEW_ALIASES.get(name, name)


def open_document_operation(freecad: FreeCADConnection, path: str) -> ToolResponse:
    result = freecad.open_document(path)
    if result.get("ok") or result.get("success"):
        return tool_ok(json.dumps(result))
    return tool_fail(json.dumps(result))


def activate_document_operation(
    freecad: FreeCADConnection, doc_name: str
) -> ToolResponse:
    result = freecad.activate_document(doc_name)
    if result.get("ok") or result.get("success"):
        return tool_ok(json.dumps(result))
    return tool_fail(json.dumps(result))


def set_tree_expanded_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    object_names: list[str] | None = None,
    mode: str = "expand",
) -> ToolResponse:
    result = freecad.set_tree_expanded(doc_name, object_names, mode)
    if result.get("ok"):
        return tool_ok(json.dumps(result))
    return tool_fail(json.dumps(result))


def select_subshapes_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    selections: list[Any] | None = None,
    clear: bool = True,
) -> ToolResponse:
    result = freecad.select_subshapes(doc_name, selections or [], clear)
    if result.get("ok"):
        return tool_ok(json.dumps(result))
    return tool_fail(json.dumps(result))


def get_selection_operation(freecad: FreeCADConnection) -> ToolResponse:
    result = freecad.get_selection()
    if result.get("ok"):
        return tool_ok(json.dumps(result))
    return tool_fail(json.dumps(result))


def get_gui_state_operation(freecad: FreeCADConnection) -> ToolResponse:
    result = freecad.get_gui_state()
    if result.get("ok"):
        return tool_ok(json.dumps(result))
    return tool_fail(json.dumps(result))


def recompute_and_wait_operation(
    freecad: FreeCADConnection, doc_name: str
) -> ToolResponse:
    result = freecad.recompute_and_wait(doc_name)
    if result.get("ok"):
        return tool_ok(json.dumps(result))
    return tool_fail(json.dumps(result))


def set_section_view_operation(
    freecad: FreeCADConnection,
    enabled: bool | None = None,
    placement: dict[str, Any] | None = None,
    base: list[float] | None = None,
    normal: list[float] | None = None,
    no_manip: bool = True,
) -> ToolResponse:
    result = freecad.set_section_view(
        enabled, placement, base, normal, no_manip
    )
    if result.get("ok"):
        return tool_ok(json.dumps(result))
    return tool_fail(json.dumps(result))


def diagnose_pocket_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    pocket_name: str,
) -> ToolResponse:
    code = _doc_preamble(doc_name) + [
        render_template_text(
            "diagnostics/diagnose_pocket.py.txt",
            pocket_name=repr(pocket_name),
        )
    ]
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(code),
        "Failed pocket diagnosis",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )


def diagnose_helix_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    helix_name: str,
) -> ToolResponse:
    code = _doc_preamble(doc_name) + [
        render_template_text(
            "diagnostics/diagnose_helix.py.txt",
            helix_name=repr(helix_name),
        )
    ]
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(code),
        "Failed helix diagnosis",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )


def compare_documents_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_a: str,
    doc_b: str,
    object_pairs: list[dict[str, str]] | list[list[str]] | None = None,
) -> ToolResponse:
    """Compare two open documents (e.g. V7 vs V8) via paired capture_state."""

    def _capture(doc_name: str, names: list[str] | None) -> dict:
        code = _doc_preamble(doc_name) + [
            render_template_text(
                "diagnostics/capture_state.py.txt",
                object_names=repr(names),
            )
        ]
        resp = _run_json_code(
            freecad,
            True,
            "\n".join(code),
            f"Failed to capture state for {doc_name}",
            screenshot=False,
            document=doc_name,
            read_only=True,
        )
        text = _response_text(resp)
        try:
            return json.loads(text)
        except Exception:
            return {"ok": False, "error": text, "doc": doc_name, "objects": []}

    pairs: list[tuple[str, str]] = []
    for item in object_pairs or []:
        if isinstance(item, dict):
            a = item.get("a") or item.get("left") or item.get("doc_a") or item.get("v7")
            b = item.get("b") or item.get("right") or item.get("doc_b") or item.get("v8")
            if a and b:
                pairs.append((str(a), str(b)))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            pairs.append((str(item[0]), str(item[1])))

    if pairs:
        names_a = [p[0] for p in pairs]
        names_b = [p[1] for p in pairs]
    else:
        names_a = None
        names_b = None

    state_a = _capture(doc_a, names_a)
    state_b = _capture(doc_b, names_b)

    if pairs:
        # Remap B object names to A names so _diff_states can pair them.
        renamed = []
        b_by_name = {o.get("name"): o for o in state_b.get("objects", [])}
        for a_name, b_name in pairs:
            row = dict(b_by_name.get(b_name) or {"name": b_name})
            row["name"] = a_name
            row["compared_as"] = b_name
            renamed.append(row)
        state_b = {**state_b, "objects": renamed}

    diff = _diff_states(state_a, state_b)
    payload = {
        "ok": True,
        "doc_a": doc_a,
        "doc_b": doc_b,
        "pairs": [{"a": a, "b": b} for a, b in pairs],
        "state_a": state_a,
        "state_b": state_b,
        "diff": diff,
    }
    return tool_ok(json.dumps(payload))
