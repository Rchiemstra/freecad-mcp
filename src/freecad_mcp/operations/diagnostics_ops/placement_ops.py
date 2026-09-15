from __future__ import annotations

import json
import logging

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import json_response, tool_fail
from ..parametric_ops.capture_state import capture_state_operation
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
    try:
        raw = freecad.placement_audit(doc_name)
    except Exception as exc:
        return tool_fail(f"Failed to audit placements: {exc}")
    if isinstance(raw, dict) and raw.get("success") is False:
        return tool_fail(
            "Failed to audit placements: " + str(raw.get("error", "unknown")),
            structured=raw,
        )
    return json_response(raw if isinstance(raw, dict) else {"ok": True, "payload": raw})



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
    resp = capture_state_operation(freecad, True, doc_name, object_names)
    if resp.isError:
        return tool_fail(
            "Failed to capture current state for diff: " + _response_text(resp),
            error_code="MALFORMED_RESPONSE",
        )
    structured = resp.structuredContent.get("data", {}) if resp.structuredContent else {}
    objects = structured.get("objects", {}) if isinstance(structured, dict) else {}
    rows = list(objects.values()) if isinstance(objects, dict) else []
    current = {"ok": True, "doc": structured.get("doc", doc_name), "objects": rows}
    return json_response(_diff_states(before, current))
