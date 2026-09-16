from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.get_dependency_graph_contract import (
    make_get_dependency_graph_uncertain,
    parse_get_dependency_graph_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def get_dependency_graph_operation(
    freecad: FreeCADConnection,
    doc_name: str, root: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.get_dependency_graph(doc_name, root)
    except Exception as exc:
        raw_result = make_get_dependency_graph_uncertain(
            "GET_DEPENDENCY_GRAPH_TRANSPORT_UNCERTAIN",
            f"get_dependency_graph response unavailable: {exc}",
            committed=None,
        )
    result = parse_get_dependency_graph_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run get_dependency_graph: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
