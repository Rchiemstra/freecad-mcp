from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import tool_fail, tool_ok
from ..parametric_ops.redo import redo_operation
from ..parametric_ops.undo import undo_operation


def get_mutation_readiness_operation(
    freecad: FreeCADConnection, doc_name: str | None = None
) -> ToolResponse:
    try:
        result = freecad.get_mutation_readiness(doc_name)
    except Exception as exc:
        return tool_fail(f"Failed to inspect mutation readiness: {exc}")
    if isinstance(result, dict) and result.get("success") is not False:
        return tool_ok(
            "Mutation readiness checked", structured=result, only_text_feedback=True
        )
    return tool_fail(
        f"Failed to inspect mutation readiness: {result}",
        structured=result if isinstance(result, dict) else None,
        error_code=result.get("error_code") if isinstance(result, dict) else None,
    )


__all__ = [
    "get_mutation_readiness_operation",
    "redo_operation",
    "undo_operation",
]
