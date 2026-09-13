from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.snapshot_contract import (
    make_snapshot_failure,
    make_snapshot_uncertain,
    parse_snapshot_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def snapshot_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "snapshot",
            {
            "doc_name": doc_name,
            },
            document_names=(doc_name,),
            operation_name="Snapshot document",
        )
        if raw_result is None:
            raw_result = make_snapshot_uncertain(
                "SNAPSHOT_TRANSPORT_UNCERTAIN",
                "snapshot response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
    except Exception as exc:
        raw_result = make_snapshot_uncertain(
            "SNAPSHOT_TRANSPORT_UNCERTAIN",
            f"Snapshot response unavailable: {exc}",
            committed=None,
        )
    result = parse_snapshot_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to snapshot document: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
