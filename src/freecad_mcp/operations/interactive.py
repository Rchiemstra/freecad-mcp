"""Interactive GUI operations: tree, selection, section, multi-document compare."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..freecad_client import FreeCADConnection
from ..responses.constants import ToolResponse
from ..responses.tool_results import json_response, tool_fail
from .diagnostics import _diff_states
from .diagnostics_ops.helpers import _response_text
from .parametric_ops.activate_document import activate_document_operation
from .parametric_ops.capture_state import capture_state_operation
from .parametric_ops.open_document import open_document_operation
from .parametric_ops.recompute_and_wait import recompute_and_wait_operation

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


def set_tree_expanded_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    object_names: list[str] | None = None,
    mode: str = "expand",
) -> ToolResponse:
    result = freecad.set_tree_expanded(doc_name, object_names, mode)
    if result.get("ok"):
        return json_response(result)
    return tool_fail(json.dumps(result), structured=result)


def select_subshapes_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    selections: list[Any] | None = None,
    clear: bool = True,
) -> ToolResponse:
    result = freecad.select_subshapes(doc_name, selections or [], clear)
    if result.get("ok"):
        return json_response(result)
    return tool_fail(json.dumps(result), structured=result)


def get_selection_operation(freecad: FreeCADConnection) -> ToolResponse:
    result = freecad.get_selection()
    if result.get("ok"):
        return json_response(result)
    return tool_fail(json.dumps(result), structured=result)


def get_gui_state_operation(freecad: FreeCADConnection) -> ToolResponse:
    result = freecad.get_gui_state()
    if result.get("ok"):
        return json_response(result)
    return tool_fail(json.dumps(result), structured=result)


def get_report_view_operation(
    freecad: FreeCADConnection,
    max_lines: int | None = 200,
    clear: bool = False,
) -> ToolResponse:
    result = freecad.get_report_view(max_lines=max_lines, clear=clear)
    if result.get("ok"):
        return json_response(result)
        return tool_fail(json.dumps(result), structured=result)


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
        return json_response(result)
    return tool_fail(json.dumps(result), structured=result)


def diagnose_pocket_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    pocket_name: str,
) -> ToolResponse:
    try:
        raw = freecad.diagnose_pocket(doc_name, pocket_name)
    except Exception as exc:
        return tool_fail(f"Failed pocket diagnosis: {exc}")
    if isinstance(raw, dict) and raw.get("success") is False:
        return tool_fail(
            "Failed pocket diagnosis: " + str(raw.get("error", "unknown")),
            structured=raw,
            error_code=str(raw.get("error_code", "DIAGNOSE_POCKET_FAILED")),
        )
    return json_response(raw if isinstance(raw, dict) else {"ok": True, "payload": raw})


def diagnose_helix_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    helix_name: str,
) -> ToolResponse:
    try:
        raw = freecad.diagnose_helix(doc_name, helix_name)
    except Exception as exc:
        return tool_fail(f"Failed helix diagnosis: {exc}")
    if isinstance(raw, dict) and raw.get("success") is False:
        return tool_fail(
            "Failed helix diagnosis: " + str(raw.get("error", "unknown")),
            structured=raw,
            error_code=str(raw.get("error_code", "DIAGNOSE_HELIX_FAILED")),
        )
    return json_response(raw if isinstance(raw, dict) else {"ok": True, "payload": raw})


def compare_documents_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_a: str,
    doc_b: str,
    object_pairs: list[dict[str, str]] | list[list[str]] | None = None,
) -> ToolResponse:
    """Compare two open documents (e.g. V7 vs V8) via paired capture_state."""

    def _capture(doc_name: str, names: list[str] | None) -> dict:
        resp = capture_state_operation(freecad, True, doc_name, names)
        if resp.isError:
            text = _response_text(resp)
            return {"ok": False, "error": text, "doc": doc_name, "objects": []}
        structured = resp.structuredContent.get("data", {}) if resp.structuredContent else {}
        if not isinstance(structured, dict):
            return {"ok": False, "error": "invalid capture_state response", "doc": doc_name, "objects": []}
        objects = structured.get("objects", {})
        rows = list(objects.values()) if isinstance(objects, dict) else []
        return {"ok": True, "doc": structured.get("doc", doc_name), "objects": rows}

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
    return json_response(payload)


__all__ = [
    "activate_document_operation",
    "compare_documents_operation",
    "diagnose_helix_operation",
    "diagnose_pocket_operation",
    "get_gui_state_operation",
    "get_report_view_operation",
    "get_selection_operation",
    "open_document_operation",
    "recompute_and_wait_operation",
    "select_subshapes_operation",
    "set_section_view_operation",
    "set_tree_expanded_operation",
]
