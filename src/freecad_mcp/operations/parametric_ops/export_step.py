from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.export_step_contract import (
    ExportStepRequest,
    make_export_step_uncertain,
    parse_export_step_response,
    DocumentName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def export_step_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    file_path: str,
    obj_names: list[str] | None = None,
) -> CallToolResult:
    request = ExportStepRequest(
        doc_name=DocumentName(doc_name),
        file_path=file_path,
        obj_names=obj_names
    )
    try:
        raw_result: object = freecad.export_step(doc_name, file_path, obj_names)
    except Exception as exc:
        raw_result = make_export_step_uncertain(
            "EXPORT_STEP_TRANSPORT_UNCERTAIN",
            f"ExportStep response unavailable: {exc}",
            committed=None,
        )
    result = parse_export_step_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run export_step: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
