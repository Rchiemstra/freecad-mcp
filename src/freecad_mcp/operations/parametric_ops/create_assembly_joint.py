from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.create_assembly_joint_contract import (
    CreateAssemblyJointRequest,
    make_create_assembly_joint_uncertain,
    parse_create_assembly_joint_response,
    AssemblyName,
    DocumentName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def create_assembly_joint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    assembly_name: str,
    joint_type: str,
    ref1_component: str,
    ref2_component: str,
    ref1_element: str = "",
    ref2_element: str = "",
    ref1_vertex: str | None = None,
    ref2_vertex: str | None = None,
    label: str | None = None,
    solve: bool = True,
    presolve: bool = True,
    recompute: bool = True,
    properties: dict[str, object] | None = None,
) -> CallToolResult:
    request = CreateAssemblyJointRequest(
        doc_name=DocumentName(doc_name),
        assembly_name=AssemblyName(assembly_name),
        joint_type=joint_type,
        ref1_component=ref1_component,
        ref2_component=ref2_component,
        ref1_element=ref1_element,
        ref2_element=ref2_element,
        ref1_vertex=ref1_vertex,
        ref2_vertex=ref2_vertex,
        label=label,
        solve=solve,
        presolve=presolve,
        recompute=recompute,
        properties=properties
    )
    try:
        raw_result: object = freecad.create_assembly_joint(doc_name, assembly_name, joint_type, ref1_component, ref2_component, ref1_element, ref2_element, ref1_vertex, ref2_vertex, label, solve, presolve, recompute, properties)
    except Exception as exc:
        raw_result = make_create_assembly_joint_uncertain(
            "CREATE_ASSEMBLY_JOINT_TRANSPORT_UNCERTAIN",
            f"CreateAssemblyJoint response unavailable: {exc}",
            committed=None,
        )
    result = parse_create_assembly_joint_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run create_assembly_joint: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
