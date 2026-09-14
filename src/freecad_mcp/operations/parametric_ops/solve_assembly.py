from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.solve_assembly_contract import (
    SolveAssemblyRequest,
    make_solve_assembly_uncertain,
    parse_solve_assembly_response,
    AssemblyName,
    DocumentName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def solve_assembly_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    assembly_name: str,
) -> CallToolResult:
    request = SolveAssemblyRequest(
        doc_name=DocumentName(doc_name),
        assembly_name=AssemblyName(assembly_name)
    )
    try:
        raw_result: object = freecad.solve_assembly(doc_name, assembly_name)
    except Exception as exc:
        raw_result = make_solve_assembly_uncertain(
            "SOLVE_ASSEMBLY_TRANSPORT_UNCERTAIN",
            f"SolveAssembly response unavailable: {exc}",
            committed=None,
        )
    result = parse_solve_assembly_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run solve_assembly: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
