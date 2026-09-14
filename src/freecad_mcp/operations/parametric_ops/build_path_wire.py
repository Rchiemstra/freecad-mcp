from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.build_path_wire_contract import (
    make_build_path_wire_failure,
    make_build_path_wire_uncertain,
    parse_build_path_wire_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def build_path_wire_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, wire_name: str, segments: object, tolerance_mm: float = 0.5, container: str | None = None, if_exists: str = "error",
) -> CallToolResult:
    if if_exists not in {"error", "skip", "replace"}:
        failure = make_build_path_wire_failure("INVALID_ARGUMENT", "if_exists must be one of: error, skip, replace")
        return tool_fail(failure["error"], structured=dict(failure), error_code=failure["error_code"])
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "build_path_wire",
            {
            "doc_name": doc_name,
            "wire_name": wire_name,
            "segments": segments,
            "tolerance_mm": tolerance_mm,
            "container": container,
            "if_exists": if_exists,
            },
            document_names=(doc_name,),
            operation_name="Build path wire",
        )
        if raw_result is None:
            raw_result = make_build_path_wire_uncertain(
                "BUILD_PATH_WIRE_TRANSPORT_UNCERTAIN",
                "build_path_wire response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
    except Exception as exc:
        raw_result = make_build_path_wire_uncertain(
            "BUILD_PATH_WIRE_TRANSPORT_UNCERTAIN",
            f"BuildPathWire response unavailable: {exc}",
            committed=None,
        )
    result = parse_build_path_wire_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to build path wire: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
