from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.create_subshape_binder_contract import (
    make_create_subshape_binder_failure,
    make_create_subshape_binder_uncertain,
    parse_create_subshape_binder_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def create_subshape_binder_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, binder_name: str, source_object: str, sub_elements: object = None, target_body: str | None = None, target_container: str | None = None, relative: bool = False, sync_placement: bool = True, if_exists: str = "error",
) -> CallToolResult:
    if if_exists not in {"error", "skip", "replace"}:
        failure = make_create_subshape_binder_failure("INVALID_ARGUMENT", "if_exists must be one of: error, skip, replace")
        return tool_fail(failure["error"], structured=dict(failure), error_code=failure["error_code"])
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "create_subshape_binder",
            {
            "doc_name": doc_name,
            "binder_name": binder_name,
            "source_object": source_object,
            "sub_elements": sub_elements,
            "target_body": target_body,
            "target_container": target_container,
            "relative": relative,
            "sync_placement": sync_placement,
            "if_exists": if_exists,
            },
            document_names=(doc_name,),
            operation_name="Create subshape binder",
        )
        if raw_result is None:
            raw_result = make_create_subshape_binder_uncertain(
                "CREATE_SUBSHAPE_BINDER_TRANSPORT_UNCERTAIN",
                "create_subshape_binder response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
    except Exception as exc:
        raw_result = make_create_subshape_binder_uncertain(
            "CREATE_SUBSHAPE_BINDER_TRANSPORT_UNCERTAIN",
            f"CreateSubshapeBinder response unavailable: {exc}",
            committed=None,
        )
    result = parse_create_subshape_binder_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to create subshape binder: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
