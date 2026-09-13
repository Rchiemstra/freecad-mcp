from __future__ import annotations

import json

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import tool_fail, tool_ok
from ...template_resources import render_template_lines
from ..p7_assembly import _run_json_code
from .helpers import _doc_missing


def body_create_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    body_name: str,
) -> ToolResponse:
    try:
        result = freecad.body_create(doc_name, body_name)
    except Exception as exc:
        return tool_fail(f"Failed to create body: {exc}")
    if not isinstance(result, dict):
        return tool_fail(
            "Failed to create body: invalid RPC response",
            error_code="INVALID_RPC_RESPONSE",
        )
    if result.get("success") is False or result.get("ok") is False:
        return tool_fail(
            f"Failed to create body: {result.get('error', result.get('message', 'unknown error'))}",
            structured=result,
            error_code=result.get("error_code"),
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=result,
        only_text_feedback=only_text_feedback,
    )

def body_set_tip_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    body_name: str,
    feature_name: str,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/body_set_tip.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        body_name=repr(body_name),
        feature_name=repr(feature_name),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to set body tip",
        screenshot=False,
        document=doc_name,
    )
