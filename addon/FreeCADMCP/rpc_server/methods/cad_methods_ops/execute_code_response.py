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
    document = options.get("document") or None
    execution = {
        "mode": "gui",
        "venue": "document_owner_thread" if document else "qt_main_thread",
        "document": document,
        "document_source": options.get("_document_source", "explicit" if document else "none"),
    }
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
                "execution": execution,
                **({"note": res["note"]} if "note" in res else {}),
            }
        )
    tb = res.get("traceback")
    document_name = str(options.get("document") or "")
    error = str(res.get("error", "Unknown error"))
    if execution["document_source"] == "active":
        error += (
            f"; omitted document resolved to active document {document!r}, so the body "
            "is scoped to its owner thread. Use a typed GUI tool such as get_gui_state for Qt access."
        )
    if "lifecycle" in error.lower() and "unavailable" in error.lower():
        error += "; use create_document / open_document first, then run execute_code in that document"
    if "generic recompute has an unresolved cross-document dependency" in error:
        error += (
            '; run execute_code with recompute="none", then call '
            f'recompute_document(doc_name={document_name!r}). The body was rolled back; '
            'it has not been rerun.'
        )
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
        "execution": execution,
    }
    for key in (
        "error_code",
        "mutation_readiness",
        "waited_for_readiness",
        "retryable",
        "committed",
        "outcome",
        "retry_safe",
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
