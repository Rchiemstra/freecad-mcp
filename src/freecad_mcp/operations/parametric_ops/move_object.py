from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.move_object_contract import (
    make_move_object_failure,
    make_move_object_uncertain,
    parse_move_object_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def move_object_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, obj_name: str, target_container: str, remove_from_old_parent: bool = True,
) -> CallToolResult:
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "move_object",
            {
            "doc_name": doc_name,
            "obj_name": obj_name,
            "target_container": target_container,
            "remove_from_old_parent": remove_from_old_parent,
            },
            document_names=(doc_name,),
            operation_name="Move object",
        )
        if raw_result is None:
            raw_result = make_move_object_uncertain(
                "MOVE_OBJECT_TRANSPORT_UNCERTAIN",
                "move_object response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
    except Exception as exc:
        raw_result = make_move_object_uncertain(
            "MOVE_OBJECT_TRANSPORT_UNCERTAIN",
            f"MoveObject response unavailable: {exc}",
            committed=None,
        )
    result = parse_move_object_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to move object: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
