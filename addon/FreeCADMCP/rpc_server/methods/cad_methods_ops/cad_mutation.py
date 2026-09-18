"""Native attribution adapter shared by typed CAD mutation handlers."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

try:
    from ....dispatch.gui_stage_clock import current_stage_clock
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.gui_stage_clock import current_stage_clock

from ...recompute_policy import assert_recompute_policy
from .mutation_readiness import document_readiness, mark_quarantined
from .mutation_readiness_wait import (
    blocking_readiness_reasons,
    settle_pending_mutation_readiness,
)

_ACTIVE_INFLIGHT: ContextVar[Any | None] = ContextVar(
    "freecad_mcp_cad_mutation_inflight", default=None
)
_ACTIVE_RPC_METHOD: ContextVar[str | None] = ContextVar(
    "freecad_mcp_cad_mutation_method", default=None
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


@contextmanager
def cad_mutation_rpc_method(method: str | None):
    """Carry the active typed RPC method name into ``run_cad_mutation``."""

    token = _ACTIVE_RPC_METHOD.set(method)
    try:
        yield
    finally:
        _ACTIVE_RPC_METHOD.reset(token)


def current_cad_mutation_rpc_method() -> str | None:
    return _ACTIVE_RPC_METHOD.get()


def _document_name(document: Any) -> str:
    return str(getattr(document, "Name", "") or "<unnamed>")


def _readiness_failure_message(blocked: list[dict[str, Any]]) -> str:
    details = []
    for item in blocked:
        name = str(item.get("document") or "<unnamed>")
        reasons = ", ".join(str(reason) for reason in item.get("reasons") or ())
        diagnostic = str(item.get("diagnostic") or "")
        description = reasons or "native readiness rejected the mutation"
        if diagnostic:
            description += f" ({diagnostic})"
        details.append(f"document {name!r}: {description}")
    return "Mutation refused because " + "; ".join(details)


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
        "error": _readiness_failure_message(blocked),
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
    warning = {
        "code": "MUTATION_NOT_READY_AFTER_COMMIT",
        "message": "Mutation committed but the document is not ready for another mutation",
    }
    if isinstance(result, dict):
        committed = dict(result)
        committed["ready_for_next_mutation"] = False
        committed["readiness_warning"] = warning
        committed["mutation_readiness"] = [readiness]
        committed["retryable"] = False
        return committed
    return {
        "success": True,
        "ok": True,
        "result": result,
        "ready_for_next_mutation": False,
        "readiness_warning": warning,
        "mutation_readiness": [readiness],
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
    document_name = _document_name(document) if document is not None else ""
    native_message = (
        str(native_result.get("message") or "")
        if isinstance(native_result, dict)
        else ""
    )
    error = f"Native compatibility mutation rejected {operation_label}"
    if document_name:
        error += f" in document {document_name!r}"
    if status:
        error += f" ({status})"
    if native_message:
        error += f": {native_message}"
    result = {
        "success": False,
        "ok": False,
        "error_code": "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        "error": error,
        "native_status": status,
    }
    committed = (
        native_result.get("committed") is True
        if isinstance(native_result, dict)
        else False
    )
    rollback_failed = _rollback_failed(native_result)
    result["committed"] = committed
    result["outcome"] = "uncertain" if committed or rollback_failed else "rejected"
    result["retry_safe"] = not committed and not rollback_failed
    if isinstance(native_result, dict):
        if native_result.get("message") is not None:
            result["native_message"] = native_result.get("message")
        for key in ("rollback_succeeded", "rollback_failed"):
            if key in native_result:
                result[key] = native_result[key]
    if rollback_failed:
        result["rollback_succeeded"] = False
        result["rollback_failed"] = True
    if document is not None:
        result["document_name"] = document_name
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


def _invoke_mutation_callback(
    callback: Callable[..., Any], document: Any, *, bind_document: bool
) -> Any:
    return callback(document) if bind_document else callback()


def run_cad_mutation(  # noqa: C901
    collaborators,
    document_name: str,
    callback: Callable[..., Any],
    *,
    structural: bool = False,
    inflight: Any = None,
    validate_after_callback: bool = True,
    native_recompute: bool = True,
    recovery_deferred: bool = False,
    postcondition: Callable[..., Any] | None = None,
    method: str | None = None,
    bind_document: bool = False,
    require_native: bool = False,
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

    rpc_method = method if method is not None else current_cad_mutation_rpc_method()
    assert_recompute_policy(
        rpc_method, native_recompute, recovery_deferred=recovery_deferred
    )

    document, lookup_error, lookup_available = _lookup_document(
        collaborators, document_name
    )
    if lookup_error is not None:
        return lookup_error
    if lookup_available and document is None:
        # No native document exists and therefore no model mutation can be
        # attributed. Let the leaf preserve its historical not-found envelope.
        return _invoke_mutation_callback(callback, None, bind_document=bind_document)

    inflight = inflight if inflight is not None else current_cad_mutation_inflight()
    clock = current_stage_clock()
    if clock is not None:
        clock.begin_admission()
    admission_failure = admit_cad_mutation(
        document,
        inflight=inflight,
        allow_pending_recompute=not native_recompute,
    )
    if clock is not None:
        clock.end_admission()
    if admission_failure is not None:
        return admission_failure

    captured: dict[str, Any] = {}

    def native_callback(*args: Any) -> Any:
        if inflight is not None:
            inflight.token.begin_mutation(rpc_method or "cad_mutation")
        if clock is not None:
            clock.begin_mutation_callback()
        admitted = args[0] if bind_document and args else document
        if bind_document:
            captured["document"] = admitted
        captured["result"] = _invoke_mutation_callback(
            callback, admitted, bind_document=bind_document
        )
        if _result_failed(captured["result"]):
            if clock is not None:
                clock.end_mutation_callback()
            raise _CadMutationRollback
        if clock is not None:
            clock.end_mutation_callback()
        return captured["result"]

    def native_postcondition(*args: Any) -> bool:
        captured["postcondition_called"] = True
        admitted = args[0] if bind_document and args else document
        if bind_document and captured.get("document") is not admitted:
            captured["result"] = {
                "success": False,
                "ok": False,
                "error_code": "DOCUMENT_IDENTITY_MISMATCH",
                "error": "Native mutation callbacks received different documents",
            }
            return False
        outcome = (
            _invoke_mutation_callback(postcondition, admitted, bind_document=bind_document)
            if postcondition is not None
            else None
        )
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
                if clock is not None:
                    clock.begin_postcondition()
                try:
                    _validate_native_callback(collaborators, admitted)
                finally:
                    if clock is not None:
                        clock.end_postcondition()
            except Exception as exc:
                captured["result"] = {
                    "success": False,
                    "ok": False,
                    "error_code": "DOCUMENT_HEALTH_DEGRADED",
                    "error": str(exc),
                }
                return False
        return True

    commit_kwargs: dict[str, Any] = {
        "structural": structural,
    }
    if bind_document:
        commit_kwargs["bind_document"] = True
    if require_native:
        commit_kwargs["require_native"] = True
    if native_recompute or postcondition is not None:
        # The postcondition keyword is an ordering contract.  An older
        # runtime must reject it before invoking ``native_callback``;
        # silently falling back would validate pre-recompute state.
        commit_kwargs["postcondition"] = native_postcondition
    if not native_recompute:
        commit_kwargs["recompute"] = False

    if clock is not None:
        clock.begin_native_commit()
    try:
        native_result = collaborators.commit_compatibility_mutation(
            document_name,
            native_callback,
            **commit_kwargs,
        )
    except LookupError:
        return _invoke_mutation_callback(callback, None, bind_document=bind_document)
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
    finally:
        if clock is not None:
            clock.end_native_commit()

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
    "cad_mutation_rpc_method",
    "current_cad_mutation_inflight",
    "current_cad_mutation_rpc_method",
    "native_mutation_rejection",
    "native_rollback_exception_result",
    "postflight_cad_mutation",
    "run_cad_mutation",
    "unsupported_native_phase_boundary",
]
