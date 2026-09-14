from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.validate_movement_follow_contract import (
    make_validate_movement_follow_failure,
    make_validate_movement_follow_uncertain,
    parse_validate_movement_follow_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def validate_movement_follow_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, source: str, dependents: object, translation: object, axis: object, angle_deg: float, restore: bool = True, tolerance: float = 1e-07,
) -> CallToolResult:
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "validate_movement_follow",
            {
            "doc_name": doc_name,
            "source": source,
            "dependents": dependents,
            "translation": translation,
            "axis": axis,
            "angle_deg": angle_deg,
            "restore": restore,
            "tolerance": tolerance,
            },
            document_names=(doc_name,),
            operation_name="Validate movement follow",
        )
        if raw_result is None:
            raw_result = make_validate_movement_follow_uncertain(
                "VALIDATE_MOVEMENT_FOLLOW_TRANSPORT_UNCERTAIN",
                "validate_movement_follow response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
    except Exception as exc:
        raw_result = make_validate_movement_follow_uncertain(
            "VALIDATE_MOVEMENT_FOLLOW_TRANSPORT_UNCERTAIN",
            f"ValidateMovementFollow response unavailable: {exc}",
            committed=None,
        )
    result = parse_validate_movement_follow_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed movement-follow validation: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
