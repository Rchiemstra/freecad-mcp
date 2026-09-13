from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.relink_references_contract import (
    make_relink_references_failure,
    make_relink_references_uncertain,
    parse_relink_references_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def relink_references_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, from_obj: str, to_obj: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "relink_references",
            {
            "doc_name": doc_name,
            "from_obj": from_obj,
            "to_obj": to_obj,
            },
            document_names=(doc_name,),
            operation_name="Relink references",
        )
        if raw_result is None:
            raw_result = make_relink_references_uncertain(
                "RELINK_REFERENCES_TRANSPORT_UNCERTAIN",
                "relink_references response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
    except Exception as exc:
        raw_result = make_relink_references_uncertain(
            "RELINK_REFERENCES_TRANSPORT_UNCERTAIN",
            f"RelinkReferences response unavailable: {exc}",
            committed=None,
        )
    result = parse_relink_references_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to relink references: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
