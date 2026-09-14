from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.export_stl_contract import (
    ExportStlRequest,
    make_export_stl_uncertain,
    parse_export_stl_response,
    DocumentName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def export_stl_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    file_path: str,
    obj_names: list[str] | None = None,
    mesh_deviation: float = 0.1,
) -> CallToolResult:
    request = ExportStlRequest(
        doc_name=DocumentName(doc_name),
        file_path=file_path,
        obj_names=obj_names,
        mesh_deviation=mesh_deviation
    )
    try:
        raw_result: object = freecad.export_stl(doc_name, file_path, obj_names, mesh_deviation)
    except Exception as exc:
        raw_result = make_export_stl_uncertain(
            "EXPORT_STL_TRANSPORT_UNCERTAIN",
            f"ExportStl response unavailable: {exc}",
            committed=None,
        )
    result = parse_export_stl_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run export_stl: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
