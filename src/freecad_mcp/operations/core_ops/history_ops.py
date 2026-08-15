from __future__ import annotations

import logging

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import tool_fail, tool_ok

logger = logging.getLogger("FreeCADMCPserver")


def undo_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    return _typed_history_response(freecad, "undo", doc_name)


def redo_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    return _typed_history_response(freecad, "redo", doc_name)


def _typed_history_response(freecad: FreeCADConnection, action: str, doc_name: str) -> ToolResponse:
    try:
        result = getattr(freecad, action)(doc_name)
    except Exception as exc:
        logger.error("Typed %s failed: %s", action, exc)
        return tool_fail(f"Failed to {action}: {exc}")
    if (
        isinstance(result, dict)
        and result.get("success") is not False
        and result.get("ok") is not False
    ):
        return tool_ok(
            f"{action.title()} performed on '{doc_name}'",
            structured=result,
            only_text_feedback=True,
        )
    failure = result.get("error", result) if isinstance(result, dict) else result
    return tool_fail(
        f"Failed to {action}: {failure}",
        structured=result if isinstance(result, dict) else None,
        error_code=result.get("error_code") if isinstance(result, dict) else None,
    )


def get_mutation_readiness_operation(
    freecad: FreeCADConnection, doc_name: str | None = None
) -> ToolResponse:
    try:
        result = freecad.get_mutation_readiness(doc_name)
    except Exception as exc:
        return tool_fail(f"Failed to inspect mutation readiness: {exc}")
    if isinstance(result, dict) and result.get("success") is not False:
        return tool_ok("Mutation readiness checked", structured=result, only_text_feedback=True)
    return tool_fail(
        f"Failed to inspect mutation readiness: {result}",
        structured=result if isinstance(result, dict) else None,
        error_code=result.get("error_code") if isinstance(result, dict) else None,
    )
