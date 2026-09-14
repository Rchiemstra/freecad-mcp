from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.run_fem_analysis_contract import (
    make_run_fem_analysis_failure,
    make_run_fem_analysis_uncertain,
    parse_run_fem_analysis_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def run_fem_analysis_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, analysis_name: str, timeout: int = 600,
) -> CallToolResult:
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "run_fem_analysis",
            {
            "doc_name": doc_name,
            "analysis_name": analysis_name,
            "timeout": timeout,
            },
            document_names=(doc_name,),
            operation_name="Run FEM analysis",
        )
        if raw_result is None:
            raw_result = make_run_fem_analysis_uncertain(
                "RUN_FEM_ANALYSIS_TRANSPORT_UNCERTAIN",
                "run_fem_analysis response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
    except Exception as exc:
        raw_result = make_run_fem_analysis_uncertain(
            "RUN_FEM_ANALYSIS_TRANSPORT_UNCERTAIN",
            f"RunFemAnalysis response unavailable: {exc}",
            committed=None,
        )
    result = parse_run_fem_analysis_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to run FEM analysis: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
