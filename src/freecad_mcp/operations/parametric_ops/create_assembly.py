from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.create_assembly_contract import (
    CreateAssemblyRequest,
    make_create_assembly_uncertain,
    parse_create_assembly_response,
    AssemblyName,
    DocumentName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def create_assembly_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    assembly_name: str = "Assembly",
    create_joint_group: bool = True,
    recompute: bool = False,
    if_exists: str = "error",
) -> CallToolResult:
    if if_exists not in {"error", "skip", "replace"}:
        return tool_fail("if_exists must be error, skip, or replace")
    request = CreateAssemblyRequest(
        doc_name=DocumentName(doc_name),
        assembly_name=AssemblyName(assembly_name),
        create_joint_group=create_joint_group,
        recompute=recompute,
        if_exists=if_exists
    )
    try:
        raw_result: object = freecad.create_assembly(doc_name, assembly_name, create_joint_group, recompute, if_exists)
    except Exception as exc:
        raw_result = make_create_assembly_uncertain(
            "CREATE_ASSEMBLY_TRANSPORT_UNCERTAIN",
            f"CreateAssembly response unavailable: {exc}",
            committed=None,
        )
    result = parse_create_assembly_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run create_assembly: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
