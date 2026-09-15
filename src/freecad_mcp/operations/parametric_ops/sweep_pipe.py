from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sweep_pipe_contract import (
    make_sweep_pipe_failure,
    make_sweep_pipe_uncertain,
    parse_sweep_pipe_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sweep_pipe_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, path_wire: str, diameter_mm: float, solid_name: str, profile_mode: str = "frenet", color: object = None, container: str | None = None, if_exists: str = "error",
) -> CallToolResult:
    if if_exists not in {"error", "skip", "replace"}:
        failure = make_sweep_pipe_failure("INVALID_ARGUMENT", "if_exists must be one of: error, skip, replace")
        return tool_fail(failure["error"], structured=dict(failure), error_code=failure["error_code"])
    try:
        raw_result: object = freecad.sweep_pipe(doc_name, path_wire, diameter_mm, solid_name, profile_mode, color, container, if_exists)
    except Exception as exc:
        raw_result = make_sweep_pipe_uncertain(
            "SWEEP_PIPE_TRANSPORT_UNCERTAIN",
            f"SweepPipe response unavailable: {exc}",
            committed=None,
        )
    result = parse_sweep_pipe_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to sweep pipe: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
