from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.import_step_contract import (
    ImportStepRequest,
    make_import_step_uncertain,
    parse_import_step_response,
    DocumentName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def import_step_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    file_path: str,
) -> CallToolResult:
    request = ImportStepRequest(
        doc_name=DocumentName(doc_name),
        file_path=file_path
    )
    try:
        raw_result: object = freecad.import_step(doc_name, file_path)
    except Exception as exc:
        raw_result = make_import_step_uncertain(
            "IMPORT_STEP_TRANSPORT_UNCERTAIN",
            f"ImportStep response unavailable: {exc}",
            committed=None,
        )
    result = parse_import_step_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run import_step: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
