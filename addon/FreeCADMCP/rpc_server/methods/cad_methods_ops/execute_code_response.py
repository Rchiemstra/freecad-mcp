"""execute_code GUI response shaping (Phase 4 slice 4F)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .execute_code_policy import flatten_recompute_errors


def finalize_gui_execute_response(
    annotate: Callable[[dict[str, Any]], dict[str, Any]],
    res: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    if res.get("ok"):
        session = res.get("session", {})
        return annotate(
            {
                "success": True,
                "message": "Python code execution completed.\nOutput: "
                + res.get("stdout", ""),
                "recompute_errors": flatten_recompute_errors(session, options),
                "session": session,
                "structured": session,
                "execution": {"mode": "gui"},
            }
        )
    tb = res.get("traceback")
    document_name = str(options.get("document") or "")
    error = str(res.get("error", "Unknown error"))
    if document_name and f"document {document_name!r}" not in error:
        error = f"execute_code failed in document {document_name!r}: {error}"
    failure = {
        "success": False,
        "error": error,
        "traceback": tb,
        "structured": tb,
        "session": res.get("session", {}),
        "message": res.get("stdout", ""),
        "is_error": True,
    }
    for key in (
        "error_code",
        "mutation_readiness",
        "waited_for_readiness",
        "retryable",
        "committed_result",
        "native_status",
        "native_message",
        "rollback_succeeded",
        "rollback_failed",
        "diagnostic",
        "document_name",
    ):
        if key in res:
            failure[key] = res[key]
    if document_name:
        failure.setdefault("document_name", document_name)
    return annotate(failure)
