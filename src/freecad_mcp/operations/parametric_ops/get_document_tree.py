from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.get_document_tree_contract import (
    make_get_document_tree_uncertain,
    parse_get_document_tree_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def get_document_tree_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    root_filter: str = "",
    max_depth: int = 4,
    include: object = None,
    include_properties: object = None,
    selected_nodes: object = None,
) -> CallToolResult:
    try:
        raw_result: object = freecad.get_document_tree(
            doc_name, root_filter, max_depth, include, include_properties, selected_nodes
        )
    except Exception as exc:
        raw_result = make_get_document_tree_uncertain(
            "GET_DOCUMENT_TREE_TRANSPORT_UNCERTAIN",
            f"get_document_tree response unavailable: {exc}",
            committed=None,
        )
    result = parse_get_document_tree_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run get_document_tree: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
