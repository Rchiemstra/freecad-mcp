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
    result = {
        "success": False,
        "ok": False,
        "error_code": "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        "error": (
            "Native compatibility mutation rejected CAD operation"
            + (f" ({status})" if status else "")
        ),
        "native_status": status,
    }
    if isinstance(native_result, dict):
        for key in ("message", "rollback_succeeded", "rollback_failed"):
            if key in native_result:
                result[f"native_{key}" if key == "message" else key] = (
                    native_result[key]
                )
    return result


def _lookup_document(collaborators, document_name: str):
    document_lookup = getattr(collaborators.freecad, "getDocument", None)
    if not callable(document_lookup):
        return None, None, False
    try:
        return document_lookup(document_name), None, True
    except Exception as exc:
        return None, str(exc), True


def _recompute_native_callback(document) -> None:
    if document is None:
        return
    recompute = getattr(document, "recompute", None)
    if callable(recompute):
        recompute()


def _validate_native_callback(collaborators, document) -> None:
    if document is None:
        return
    collaborators.validate_document_invariants(document)


def _invoke_bound(callback: Callable[..., Any], document: Any, bind_document: bool):
    return callback(document) if bind_document else callback()


def run_cad_mutation(
    collaborators,
    document_name: str,
    callback: Callable[..., Any],
    *,
    structural: bool = False,
    postcondition: Callable[..., Any] | None = None,
    bind_document: bool = False,
):
    """Run one typed CAD callback through one native compatibility commit.

    The native result is an internal attribution result.  The RPC caller keeps
    receiving the historical CAD callback envelope.  Failure-shaped legacy
    values escape through a private exception so the native coordinator rolls
    back before the original value is restored. ``bind_document`` passes the
    exact document resolved here to the apply and inspection callbacks.
    """

    if postcondition is not None and not callable(postcondition):
        raise TypeError("postcondition must be callable")

    document, lookup_error, lookup_available = _lookup_document(
        collaborators, document_name
    )
    if lookup_error is not None:
        return lookup_error
    if lookup_available and document is None:
        # No native document exists and therefore no model mutation can be
        # attributed. Let the leaf preserve its historical not-found envelope.
        return _invoke_bound(callback, document, bind_document)

    captured: dict[str, Any] = {}

    def native_callback():
        captured["result"] = _invoke_bound(callback, document, bind_document)
        if _result_failed(captured["result"]):
            raise _CadMutationRollback
        try:
            _recompute_native_callback(document)
        except Exception as exc:
            captured["result"] = {
                "success": False,
                "ok": False,
                "error_code": "DOCUMENT_HEALTH_DEGRADED",
                "error": str(exc),
            }
            raise _CadMutationRollback from exc

        if postcondition is not None:
            try:
                outcome = _invoke_bound(postcondition, document, bind_document)
            except Exception as exc:
                captured["result"] = {
                    "success": False,
                    "ok": False,
                    "error_code": "CAD_POSTCONDITION_FAILED",
                    "error": str(exc),
                }
                raise _CadMutationRollback from exc
            if outcome is not None and outcome is not True:
                captured["result"] = outcome
            if outcome is not None and _result_failed(outcome):
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
