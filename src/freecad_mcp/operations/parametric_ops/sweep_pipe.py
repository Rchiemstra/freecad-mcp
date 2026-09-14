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
        result = make_sweep_pipe_failure("INVALID_ARGUMENT", "if_exists must be one of: error, skip, replace")
        return tool_fail(result["error"], structured=dict(result), error_code=result["error_code"])
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "sweep_pipe",
            {
            "doc_name": doc_name,
            "path_wire": path_wire,
            "diameter_mm": diameter_mm,
            "solid_name": solid_name,
            "profile_mode": profile_mode,
            "color": color,
            "container": container,
            "if_exists": if_exists,
            },
            document_names=(doc_name,),
            operation_name="Sweep pipe",
        )
        if raw_result is None:
            raw_result = make_sweep_pipe_uncertain(
                "SWEEP_PIPE_TRANSPORT_UNCERTAIN",
                "sweep_pipe response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
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
