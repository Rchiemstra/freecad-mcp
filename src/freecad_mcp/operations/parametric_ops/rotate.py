from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.rotate_contract import (
    RotateRequest,
    make_rotate_uncertain,
    parse_rotate_response,
    DocumentName,
    ObjectName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def rotate_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    axis_x: float,
    axis_y: float,
    axis_z: float,
    angle_deg: float,
    center_x: float = 0.0,
    center_y: float = 0.0,
    center_z: float = 0.0,
) -> CallToolResult:
    request = RotateRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name),
        axis_x=axis_x,
        axis_y=axis_y,
        axis_z=axis_z,
        angle_deg=angle_deg,
        center_x=center_x,
        center_y=center_y,
        center_z=center_z
    )
    try:
        raw_result: object = freecad.rotate(doc_name, obj_name, axis_x, axis_y, axis_z, angle_deg, center_x, center_y, center_z)
    except Exception as exc:
        raw_result = make_rotate_uncertain(
            "ROTATE_TRANSPORT_UNCERTAIN",
            f"Rotate response unavailable: {exc}",
            committed=None,
        )
    result = parse_rotate_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run rotate: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
