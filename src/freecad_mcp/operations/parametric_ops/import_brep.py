from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.import_brep_contract import (
    ImportBrepRequest,
    make_import_brep_uncertain,
    parse_import_brep_response,
    DocumentName,
    ObjectName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def import_brep_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    file_path: str,
    obj_name: str = "BRepImport",
) -> CallToolResult:
    request = ImportBrepRequest(
        doc_name=DocumentName(doc_name),
        file_path=file_path,
        obj_name=ObjectName(obj_name)
    )
    try:
        raw_result: object = freecad.import_brep(doc_name, file_path, obj_name)
    except Exception as exc:
        raw_result = make_import_brep_uncertain(
            "IMPORT_BREP_TRANSPORT_UNCERTAIN",
            f"ImportBrep response unavailable: {exc}",
            committed=None,
        )
    result = parse_import_brep_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run import_brep: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
