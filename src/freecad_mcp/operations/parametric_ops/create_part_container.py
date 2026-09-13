from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.create_part_container_contract import (
    make_create_part_container_failure,
    make_create_part_container_uncertain,
    parse_create_part_container_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def create_part_container_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, part_name: str, parent_container: str | None = None, if_exists: str = "error",
) -> CallToolResult:
    if if_exists not in {"error", "skip", "replace"}:
        result = make_create_part_container_failure("INVALID_ARGUMENT", "if_exists must be one of: error, skip, replace")
        return tool_fail(result["error"], structured=dict(result), error_code=result["error_code"])
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "create_part_container",
            {
            "doc_name": doc_name,
            "part_name": part_name,
            "parent_container": parent_container,
            "if_exists": if_exists,
            },
            document_names=(doc_name,),
            operation_name="Create part container",
        )
        if raw_result is None:
            raw_result = make_create_part_container_uncertain(
                "CREATE_PART_CONTAINER_TRANSPORT_UNCERTAIN",
                "create_part_container response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
    except Exception as exc:
        raw_result = make_create_part_container_uncertain(
            "CREATE_PART_CONTAINER_TRANSPORT_UNCERTAIN",
            f"CreatePartContainer response unavailable: {exc}",
            committed=None,
        )
    result = parse_create_part_container_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to create part container: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
