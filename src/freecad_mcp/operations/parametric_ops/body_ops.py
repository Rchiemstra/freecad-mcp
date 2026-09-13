from __future__ import annotations

import json

from ..._shared.protocol.body_create_contract import (
    BodyCreateRequest,
    BodyName,
    DocumentName,
    parse_body_create_response,
)
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
    request = BodyCreateRequest(
        doc_name=DocumentName(doc_name),
        body_name=BodyName(body_name),
    )
    try:
        raw_result: object = freecad.body_create(request.doc_name, request.body_name)
    except Exception as exc:
        return tool_fail(f"Failed to create body: {exc}")
    result = parse_body_create_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create body: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
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
