from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.export_brep_contract import (
    ExportBrepRequest,
    make_export_brep_uncertain,
    parse_export_brep_response,
    DocumentName,
    ObjectName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def export_brep_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
    file_path: str,
) -> CallToolResult:
    request = ExportBrepRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name),
        file_path=file_path
    )
    try:
        raw_result: object = freecad.export_brep(doc_name, obj_name, file_path)
    except Exception as exc:
        raw_result = make_export_brep_uncertain(
            "EXPORT_BREP_TRANSPORT_UNCERTAIN",
            f"ExportBrep response unavailable: {exc}",
            committed=None,
        )
    result = parse_export_brep_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run export_brep: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
