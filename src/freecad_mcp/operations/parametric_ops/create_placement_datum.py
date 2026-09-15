from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.create_placement_datum_contract import (
    make_create_placement_datum_failure,
    make_create_placement_datum_uncertain,
    parse_create_placement_datum_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def create_placement_datum_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, owner_body: str, name: str, source: str, relative: bool = True, offset: object = None,
) -> CallToolResult:
    try:
        raw_result: object = freecad.create_placement_datum(doc_name, owner_body, name, source, relative, offset)
    except Exception as exc:
        raw_result = make_create_placement_datum_uncertain(
            "CREATE_PLACEMENT_DATUM_TRANSPORT_UNCERTAIN",
            f"CreatePlacementDatum response unavailable: {exc}",
            committed=None,
        )
    result = parse_create_placement_datum_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to create placement-aware datum: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
