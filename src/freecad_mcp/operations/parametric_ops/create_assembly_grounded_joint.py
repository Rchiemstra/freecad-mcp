from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.create_assembly_grounded_joint_contract import (
    CreateAssemblyGroundedJointRequest,
    make_create_assembly_grounded_joint_uncertain,
    parse_create_assembly_grounded_joint_response,
    AssemblyName,
    ComponentName,
    DocumentName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def create_assembly_grounded_joint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    assembly_name: str,
    component_name: str,
    label: str | None = None,
    recompute: bool = True,
) -> CallToolResult:
    request = CreateAssemblyGroundedJointRequest(
        doc_name=DocumentName(doc_name),
        assembly_name=AssemblyName(assembly_name),
        component_name=ComponentName(component_name),
        label=label,
        recompute=recompute
    )
    try:
        raw_result: object = freecad.create_assembly_grounded_joint(doc_name, assembly_name, component_name, label, recompute)
    except Exception as exc:
        raw_result = make_create_assembly_grounded_joint_uncertain(
            "CREATE_ASSEMBLY_GROUNDED_JOINT_TRANSPORT_UNCERTAIN",
            f"CreateAssemblyGroundedJoint response unavailable: {exc}",
            committed=None,
        )
    result = parse_create_assembly_grounded_joint_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run create_assembly_grounded_joint: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
