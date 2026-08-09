"""Native attribution adapter shared by typed CAD mutation handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class _CadMutationRollback(RuntimeError):
    """Escape a historical failure result through the native rollback boundary."""


def _result_failed(result: Any) -> bool:
    if isinstance(result, dict):
        return result.get("success") is False or result.get("ok") is False
    if isinstance(result, list):
        return False
    return result is not True


def _native_rejection(native_result: Any) -> dict[str, Any]:
    status = native_result.get("status") if isinstance(native_result, dict) else None
    return {
        "success": False,
        "ok": False,
        "error_code": "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        "error": (
            "Native compatibility mutation rejected CAD operation"
            + (f" ({status})" if status else "")
        ),
    }


def _lookup_document(collaborators, document_name: str):
    document_lookup = getattr(collaborators.freecad, "getDocument", None)
    if not callable(document_lookup):
        return None, None, False
    try:
        return document_lookup(document_name), None, True
    except Exception as exc:
        return None, str(exc), True


def _validate_native_callback(collaborators, document) -> None:
    if document is None:
        return
    recompute = getattr(document, "recompute", None)
    if callable(recompute):
        recompute()
    collaborators.validate_document_invariants(document)


def run_cad_mutation(
    collaborators,
    document_name: str,
    callback: Callable[[], Any],
    *,
    structural: bool = False,
):
    """Run one typed CAD callback through one native compatibility commit.

    The native result is an internal attribution result.  The RPC caller keeps
    receiving the historical CAD callback envelope.  Failure-shaped legacy
    values escape through a private exception so the native coordinator rolls
    back before the original value is restored.
    """

    document, lookup_error, lookup_available = _lookup_document(
        collaborators, document_name
    )
    if lookup_error is not None:
        return lookup_error
    if lookup_available and document is None:
        # No native document exists and therefore no model mutation can be
        # attributed. Let the leaf preserve its historical not-found envelope.
        return callback()

    captured: dict[str, Any] = {}

    def native_callback():
        captured["result"] = callback()
        if _result_failed(captured["result"]):
            raise _CadMutationRollback
        try:
            _validate_native_callback(collaborators, document)
        except Exception as exc:
            captured["result"] = {
                "success": False,
                "ok": False,
                "error_code": "DOCUMENT_HEALTH_DEGRADED",
                "error": str(exc),
            }
            raise _CadMutationRollback from exc
        return captured["result"]

    try:
        native_result = collaborators.commit_compatibility_mutation(
            document_name, native_callback, structural=structural
        )
    except _CadMutationRollback:
        return captured["result"]

    if (
        isinstance(native_result, dict)
        and native_result.get("status") == "Committed"
        and native_result.get("committed") is True
        and "result" in captured
    ):
        return captured["result"]
    return _native_rejection(native_result)


__all__ = ["run_cad_mutation"]
