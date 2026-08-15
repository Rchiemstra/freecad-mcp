"""Native attribution adapter shared by typed CAD mutation handlers."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from .mutation_readiness import document_readiness, mark_quarantined
from .mutation_readiness_wait import (
    blocking_readiness_reasons,
    settle_pending_mutation_readiness,
)

_ACTIVE_INFLIGHT: ContextVar[Any | None] = ContextVar(
    "freecad_mcp_cad_mutation_inflight", default=None
)


class _CadMutationRollback(RuntimeError):
    """Escape a historical failure result through the native rollback boundary."""


def _result_failed(result: Any) -> bool:
    if isinstance(result, dict):
        return result.get("success") is False or result.get("ok") is False
    if isinstance(result, list):
        return False
    return result is not True


@contextmanager
def cad_mutation_inflight(inflight: Any):
    """Carry the request cancellation token into a GUI-thread CAD callback."""

    token = _ACTIVE_INFLIGHT.set(inflight)
    try:
        yield
    finally:
        _ACTIVE_INFLIGHT.reset(token)


def current_cad_mutation_inflight() -> Any:
    return _ACTIVE_INFLIGHT.get()


def _pause_is_already_admitted(
    item: dict[str, Any], reasons: list[str] | None = None
) -> bool:
    return (list(item.get("reasons") or ()) if reasons is None else reasons) == [
        "automation_paused"
    ] and item.get("active_write_count", 0) > 0


def admit_cad_mutation(
    document: Any,
    *,
    inflight: Any = None,
    allow_pending_recompute: bool = False,
) -> dict[str, Any] | None:
    """Reject unsafe writes, after at most one explicit recompute settle.

    A local pause is intentionally not retroactive: the request that was
    admitted before the operator pressed Pause may complete, but no later
    request may enter the native mutation boundary.
    """

    readiness, waited_for_readiness = settle_pending_mutation_readiness(
        (document,),
        inflight=inflight,
        allow_pending_recompute=allow_pending_recompute,
    )
    blocked = []
    for item in readiness:
        reasons = blocking_readiness_reasons(
            item, allow_pending_recompute=allow_pending_recompute
        )
        if reasons and not _pause_is_already_admitted(item, reasons):
            blocked.append(item)
    if not blocked:
        return None
    return {
        "success": False,
        "ok": False,
        "error_code": "MUTATION_NOT_READY",
        "error": "document is not ready for mutation",
        "mutation_readiness": blocked,
        "waited_for_readiness": waited_for_readiness,
        "retryable": any(
            reason
            in {
                "native_recomputing",
                "pending_recompute",
                "pending_object_removal",
                "collaboration_notifications_replaying",
                "native_not_ready",
            }
            for item in blocked
            for reason in item["reasons"]
        ),
    }


def postflight_cad_mutation(
    document: Any,
    result: Any,
    *,
    allow_pending_recompute: bool = False,
    include_failure_readiness: bool = False,
) -> Any:
    """Check readiness after a native write without obscuring leaf failures."""

    readiness = document_readiness(document)
    reasons = blocking_readiness_reasons(
        readiness, allow_pending_recompute=allow_pending_recompute
    )
    if _result_failed(result):
        # A callback's historical error remains authoritative.  Structured
        # execute_code opts into healthy post-rollback evidence; typed leaves
        # retain their historical object/envelope identity unless blocked.
        if isinstance(result, dict) and (reasons or include_failure_readiness):
            result = dict(result)
            result.setdefault("mutation_readiness", [readiness])
            result.setdefault("retryable", not reasons)
        return result
    if not reasons or _pause_is_already_admitted(readiness, reasons):
        return result
    return {
        "success": False,
        "ok": False,
        "error_code": "MUTATION_NOT_READY_AFTER_COMMIT",
        "error": "Mutation committed but the document is not ready for another mutation",
        "mutation_readiness": [readiness],
        "committed_result": result,
        "retryable": False,
    }


def _rollback_failed(native_result: Any) -> bool:
    if not isinstance(native_result, dict):
        return False
    return (
        native_result.get("rollback_succeeded") is False
        or native_result.get("rollback_failed") is True
        or native_result.get("status") in {"RollbackFailed", "RollbackFailure"}
    )


def native_mutation_rejection(
    native_result: Any,
    document: Any = None,
    *,
    operation_label: str = "CAD operation",
) -> dict[str, Any]:
    """Return a structured native rejection and quarantine failed rollback."""

    status = native_result.get("status") if isinstance(native_result, dict) else None
    if _rollback_failed(native_result):
        mark_quarantined(document, "native compatibility mutation rollback failed")
    result = {
        "success": False,
        "ok": False,
        "error_code": "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        "error": (
            f"Native compatibility mutation rejected {operation_label}"
            + (f" ({status})" if status else "")
        ),
        "native_status": status,
    }
    if isinstance(native_result, dict):
        if native_result.get("message") is not None:
            result["native_message"] = native_result.get("message")
        for key in ("rollback_succeeded", "rollback_failed"):
            if key in native_result:
                result[key] = native_result[key]
    if document is not None:
        readiness = document_readiness(document)
        result["mutation_readiness"] = [readiness]
        result["retryable"] = readiness["ready"]
    return result


def unsupported_native_phase_boundary(
    operation: str,
    diagnostic: str,
) -> dict[str, Any]:
    """Reject a solver flow that cannot honor apply/recompute/postcondition order."""

    return {
        "success": False,
        "ok": False,
        "error_code": "UNSUPPORTED_NATIVE_PHASE_BOUNDARY",
        "error": (
            f"{operation} requires mutation work on both sides of recompute; "
            "the native compatibility boundary cannot run it atomically"
        ),
        "operation": operation,
        "diagnostic": diagnostic,
        "retryable": False,
    }


def native_rollback_exception_result(
    document: Any,
    exception: Exception,
) -> dict[str, Any] | None:
    """Classify an exception as a failed rollback only with native evidence."""

    readiness = document_readiness(document)
    rollback_not_restored = bool(
        readiness.get("collaboration_poisoned")
        or readiness.get("quarantined")
        or readiness.get("pending_transaction")
        or readiness.get("transaction_locked")
        or readiness.get("booked_transaction_id") not in (None, 0)
    )
    if not rollback_not_restored:
        return None
    mark_quarantined(
        document,
        f"native compatibility mutation rollback failed: {exception}",
    )
    readiness = document_readiness(document)
    return {
        "success": False,
        "ok": False,
        "error_code": "TRANSACTION_ROLLBACK_FAILED",
        "error": "Native compatibility mutation rollback failed",
        "diagnostic": str(exception),
        "mutation_readiness": [readiness],
        "retryable": False,
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
    collaborators.validate_document_invariants(document)


def run_cad_mutation(  # noqa: C901
    collaborators,
    document_name: str,
    callback: Callable[[], Any],
    *,
    structural: bool = False,
    inflight: Any = None,
    validate_after_callback: bool = True,
    native_recompute: bool = True,
    postcondition: Callable[[], Any] | None = None,
):
    """Run one typed CAD callback through one native compatibility commit.

    The native result is an internal attribution result.  The RPC caller keeps
    receiving the historical CAD callback envelope.  Failure-shaped legacy
    values escape through a private exception so the native coordinator rolls
    back before the original value is restored.
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
        return callback()

    inflight = inflight if inflight is not None else current_cad_mutation_inflight()
    admission_failure = admit_cad_mutation(
        document,
        inflight=inflight,
        allow_pending_recompute=not native_recompute,
    )
    if admission_failure is not None:
        return admission_failure

    captured: dict[str, Any] = {}

    def native_callback():
        captured["result"] = callback()
        if _result_failed(captured["result"]):
            raise _CadMutationRollback
        return captured["result"]

    def native_postcondition():
        captured["postcondition_called"] = True
        outcome = postcondition() if postcondition is not None else None
        if outcome is not None and outcome is not True:
            # A typed postcondition may replace the provisional callback
            # envelope with its post-recompute result.
            captured["result"] = outcome
        if outcome is not None and _result_failed(outcome):
            return False
        if validate_after_callback:
            try:
                # For eager mutations the native coordinator has already
                # completed the sole authoritative recompute.  This callback
                # is deliberately read-only.
                _validate_native_callback(collaborators, document)
            except Exception as exc:
                captured["result"] = {
                    "success": False,
                    "ok": False,
                    "error_code": "DOCUMENT_HEALTH_DEGRADED",
                    "error": str(exc),
                }
                return False
        return True

    try:
        if native_recompute:
            # The postcondition keyword is an ordering contract.  An older
            # runtime must reject it before invoking ``native_callback``;
            # silently falling back would validate pre-recompute state.
            native_result = collaborators.commit_compatibility_mutation(
                document_name,
                native_callback,
                structural=structural,
                postcondition=native_postcondition,
            )
        elif postcondition is not None:
            native_result = collaborators.commit_compatibility_mutation(
                document_name,
                native_callback,
                structural=structural,
                recompute=False,
                postcondition=native_postcondition,
            )
        else:
            native_result = collaborators.commit_compatibility_mutation(
                document_name,
                native_callback,
                structural=structural,
                recompute=False,
            )
    except _CadMutationRollback:
        return postflight_cad_mutation(
            document,
            captured["result"],
            allow_pending_recompute=not native_recompute,
        )
    except Exception as exc:
        # A failed native rollback replaces the private callback marker with a
        # regular Python exception.  Preserve ordinary callback exceptions,
        # but never let a poisoned or transaction-stuck document escape the
        # typed quarantine boundary.
        rollback_failure = native_rollback_exception_result(document, exc)
        if rollback_failure is None:
            raise
        return rollback_failure

    if (
        isinstance(native_result, dict)
        and native_result.get("status") == "Committed"
        and native_result.get("committed") is True
        and "result" in captured
    ):
        if (native_recompute or postcondition is not None) and not captured.get(
            "postcondition_called"
        ):
            mark_quarantined(
                document,
                "native compatibility mutation committed without its requested postcondition",
            )
            return {
                "success": False,
                "ok": False,
                "error_code": "NATIVE_POSTCONDITION_NOT_RUN",
                "error": "Native runtime committed without running the requested postcondition",
                "mutation_readiness": [document_readiness(document)],
                "retryable": False,
            }
        return postflight_cad_mutation(
            document,
            captured["result"],
            allow_pending_recompute=not native_recompute,
        )
    if (
        isinstance(native_result, dict)
        and native_result.get("status") == "PostconditionFailed"
        and captured.get("postcondition_called")
        and "result" in captured
        and _result_failed(captured["result"])
    ):
        return postflight_cad_mutation(
            document,
            captured["result"],
            allow_pending_recompute=not native_recompute,
        )
    return native_mutation_rejection(native_result, document)


__all__ = [
    "admit_cad_mutation",
    "cad_mutation_inflight",
    "current_cad_mutation_inflight",
    "native_mutation_rejection",
    "native_rollback_exception_result",
    "postflight_cad_mutation",
    "run_cad_mutation",
    "unsupported_native_phase_boundary",
]
