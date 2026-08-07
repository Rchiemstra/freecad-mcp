from __future__ import annotations

import json
import logging

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import json_response, tool_fail
from ...template_resources import render_template_text
from ..p7_assembly import _doc_preamble, _run_json_code
from .helpers import _response_text

logger = logging.getLogger("FreeCADMCPserver")

def placement_audit_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
) -> ToolResponse:
    """M3 — audit placements: per Body/Part list Placement, getGlobalPlacement()
    base, and the cross-body datums that reference it. Read-only; returns JSON
    ``{ok, doc, bodies: [{name, type, placement_base, placement_rotation,
    global_placement_base, cross_body_datums}]}``.
    """
    code = [*_doc_preamble(doc_name), render_template_text(
        "diagnostics/placement_audit.py.txt",
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to audit placements", screenshot=False, document=doc_name,
        read_only=True,
    )

def relink_references_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    from_obj: str,
    to_obj: str,
) -> ToolResponse:
    """M5 — re-point every reference to ``from_obj`` so it points to ``to_obj``,
    across all link-type properties of all document objects. Makes rebuilds
    non-destructive. Returns JSON ``{ok, from, to, relinked, count}``.
    """
    code = [*_doc_preamble(doc_name), render_template_text(
        "diagnostics/relink_references.py.txt",
        from_obj=repr(from_obj),
        to_obj=repr(to_obj),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to relink references", screenshot=False, document=doc_name,
    )

def capture_state_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_names: list[str] | None = None,
) -> ToolResponse:
    """I10 — capture a compact geometric state (placement + bbox + face/edge
    counts) for ``object_names`` (all objects when None). The returned JSON can
    be passed to ``geometric_diff`` to produce a text-only diff when a viewable
    image can't be returned (P10 fallback).
    """
    code = [*_doc_preamble(doc_name), render_template_text(
        "diagnostics/capture_state.py.txt",
        object_names=repr(object_names),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to capture state", screenshot=False, document=doc_name,
        read_only=True,
    )

def _diff_states(before: dict, current: dict) -> dict:
    before_objs = {o["name"]: o for o in before.get("objects", [])}
    current_objs = {o["name"]: o for o in current.get("objects", [])}
    diffs = []
    for name in sorted(set(before_objs) | set(current_objs)):
        b = before_objs.get(name)
        c = current_objs.get(name)
        entry = {
            "name": name,
            "bbox_before": b.get("bbox") if b else None,
            "bbox_after": c.get("bbox") if c else None,
            "placement_before": {
                "base": b.get("placement_base"),
                "rotation": b.get("placement_rotation"),
            } if b else None,
            "placement_after": {
                "base": c.get("placement_base"),
                "rotation": c.get("placement_rotation"),
            } if c else None,
            "faces_before": b.get("face_count") if b else None,
            "faces_after": c.get("face_count") if c else None,
            "added": b is None,
            "removed": c is None,
        }
        fb = entry["faces_before"]
        fa = entry["faces_after"]
        if fb is not None and fa is not None and fa > fb:
            entry["faces_added"] = fa - fb
            entry["faces_removed"] = 0
        elif fb is not None and fa is not None and fb > fa:
            entry["faces_added"] = 0
            entry["faces_removed"] = fb - fa
        else:
            entry["faces_added"] = 0
            entry["faces_removed"] = 0
        entry["changed"] = (
            entry["added"] or entry["removed"]
            or entry["bbox_before"] != entry["bbox_after"]
            or entry["placement_before"] != entry["placement_after"]
            or entry["faces_added"] or entry["faces_removed"]
        )
        diffs.append(entry)
    return {"ok": True, "doc": current.get("doc", before.get("doc")), "diffs": diffs}

def geometric_diff_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    before: dict,
    object_names: list[str] | None = None,
) -> ToolResponse:
    """I10 — structured geometric diff between a captured ``before`` state and
    the current document state. The P10 text-only fallback: returns JSON
    ``{ok, doc, diffs: [{name, bbox_before/after, placement_before/after,
    faces_added/removed, changed}]}`` when a viewable image can't be returned.
    """
    code = [*_doc_preamble(doc_name), render_template_text(
        "diagnostics/capture_state.py.txt",
        object_names=repr(object_names),
    )]
    resp = _run_json_code(
        freecad, True, "\n".join(code),
        "Failed to capture state for diff", screenshot=False, document=doc_name,
        read_only=True,
    )
    text = _response_text(resp)
    try:
        current = json.loads(text)
    except Exception:
        return tool_fail(
            "Failed to capture current state for diff: " + text,
            error_code="MALFORMED_RESPONSE",
        )
    return json_response(_diff_states(before, current))
