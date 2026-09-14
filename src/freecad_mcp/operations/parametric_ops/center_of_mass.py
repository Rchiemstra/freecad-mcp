from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.center_of_mass_contract import (
    CenterOfMassRequest,
    make_center_of_mass_uncertain,
    parse_center_of_mass_response,
    DocumentName,
    ObjectName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def center_of_mass_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
) -> CallToolResult:
    request = CenterOfMassRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name)
    )
    try:
        raw_result: object = freecad.center_of_mass(doc_name, obj_name)
    except Exception as exc:
        raw_result = make_center_of_mass_uncertain(
            "CENTER_OF_MASS_TRANSPORT_UNCERTAIN",
            f"CenterOfMass response unavailable: {exc}",
            committed=None,
        )
    result = parse_center_of_mass_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run center_of_mass: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
