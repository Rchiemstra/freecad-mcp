"""Native attribution adapter shared by typed CAD mutation handlers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...._shared.protocol.body_create_contract import (
    BodyCreateCollaborators,
    BodyDocument,
    BodyReadDocument,
    DocumentName,
)


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
    committed = (
        native_result.get("committed") is True
        if isinstance(native_result, dict)
        else False
    )
    rollback_failed = status == "RollbackFailed"
    result = {
        "success": False,
        "ok": False,
        "error_code": "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        "error": (
            "Native compatibility mutation rejected CAD operation"
            + (f" ({status})" if status else "")
        ),
        "native_status": status,
        "committed": committed,
        "outcome": "uncertain" if committed or rollback_failed else "rejected",
        "retry_safe": not committed and not rollback_failed,
    }
    if isinstance(native_result, dict):
        for key in ("message", "rollback_succeeded", "rollback_failed"):
            if key in native_result:
                result[f"native_{key}" if key == "message" else key] = (
                    native_result[key]
                )
    if rollback_failed:
        result["rollback_succeeded"] = False
        result["rollback_failed"] = True
    return result


def _lookup_document(
    collaborators: Any, document_name: str
) -> tuple[Any, str | None, bool]:
    document_lookup = getattr(collaborators.freecad, "getDocument", None)
    if not callable(document_lookup):
        return None, None, False
    try:
        return document_lookup(document_name), None, True
    except Exception as exc:
        return None, str(exc), True


def _recompute_native_callback(document: Any) -> None:
    if document is None:
        return
    recompute = getattr(document, "recompute", None)
    if callable(recompute):
        recompute()


def _validate_native_callback(collaborators: Any, document: Any) -> None:
    if document is None:
        return
    collaborators.validate_document_invariants(document)


def _invoke_bound(
    callback: Callable[..., Any], document: Any, bind_document: bool
) -> Any:
    return callback(document) if bind_document else callback()


def _set_captured_failure(
    captured: dict[str, Any], error_code: str, error: object
) -> None:
    captured["result"] = {
        "success": False,
        "ok": False,
        "error_code": error_code,
        "error": str(error),
    }


def _capture_postcondition(
    captured: dict[str, Any],
    postcondition: Callable[..., Any] | None,
    document: Any,
    *,
    bind_document: bool,
) -> bool:
    if postcondition is None:
        return True
    try:
        outcome = _invoke_bound(postcondition, document, bind_document)
    except Exception as exc:
        _set_captured_failure(captured, "CAD_POSTCONDITION_FAILED", exc)
        return False
    if outcome is not None and outcome is not True:
        captured["result"] = outcome
    return outcome is None or not _result_failed(outcome)


def _capture_validation(
    collaborators: Any, captured: dict[str, Any], document: Any
) -> bool:
    try:
        _validate_native_callback(collaborators, document)
    except Exception as exc:
        _set_captured_failure(captured, "DOCUMENT_HEALTH_DEGRADED", exc)
        return False
    return True


def _native_recompute_result(native_result: Any, captured: dict[str, Any]) -> Any:
    status = native_result.get("status") if isinstance(native_result, dict) else None
    if (
        status == "PostconditionFailed"
        and captured.get("postcondition_called")
        and _result_failed(captured.get("result"))
    ):
        captured_result = captured["result"]
        if isinstance(captured_result, dict):
            captured_result = dict(captured_result)
            captured_result.setdefault("committed", False)
            captured_result.setdefault("rollback_succeeded", True)
            captured_result.setdefault("rollback_failed", False)
        return captured_result
    native_committed = (
        native_result.get("committed") is True
        if isinstance(native_result, dict)
        else False
    )
    if (
        status != "Committed"
        or not native_committed
        or "result" not in captured
    ):
        return _native_rejection(native_result)
    if not captured.get("postcondition_called"):
        return {
            "success": False,
            "ok": False,
            "error_code": "NATIVE_POSTCONDITION_NOT_RUN",
            "error": "Native runtime committed without running the postcondition",
            "committed": True,
            "outcome": "uncertain",
            "retry_safe": False,
        }
    return captured["result"]


def _run_native_recompute_mutation(
    collaborators: Any,
    document_name: str,
    callback: Callable[..., Any],
    *,
    structural: bool,
    postcondition: Callable[..., Any] | None,
    bind_document: bool,
    require_native: bool,
) -> Any:
    """Run inspection and validation in the native post-recompute phase."""

    if not bind_document:
        raise ValueError("native_recompute requires bind_document=True")

    captured: dict[str, Any] = {}

    def native_callback(document: Any) -> Any:
        captured["document"] = document
        captured["result"] = callback(document)
        if _result_failed(captured["result"]):
            raise _CadMutationRollback
        return captured["result"]

    def native_postcondition(document: Any) -> bool:
        captured["postcondition_called"] = True
        if captured.get("document") is not document:
            _set_captured_failure(
                captured,
                "DOCUMENT_IDENTITY_MISMATCH",
                "Native mutation callbacks received different documents",
            )
            return False
        if not _capture_postcondition(
            captured, postcondition, document, bind_document=True
        ):
            return False
        return _capture_validation(collaborators, captured, document)

    try:
        native_result = collaborators.commit_compatibility_mutation(
            document_name,
            native_callback,
            structural=structural,
            postcondition=native_postcondition,
            bind_document=True,
            require_native=require_native,
        )
    except LookupError:
        # Preserve the leaf's typed missing-document envelope without entering
        # a mutation callback or touching the model.
        return callback(None)
    except _CadMutationRollback:
        return captured["result"]

    return _native_recompute_result(native_result, captured)


_MISSING_BODY_RESULT = object()


@dataclass(slots=True)
class _NativeBodyMutationState:
    """Typed provisional state that cannot be released before native commit."""

    document: BodyDocument | None = None
    result: object = _MISSING_BODY_RESULT
    postcondition_called: bool = False


def _body_native_result(
    native_result: object, state: _NativeBodyMutationState
) -> object:
    """Release a provisional Body result only after a verified native commit."""

    if not isinstance(native_result, dict):
        return _native_rejection(native_result)
    status = native_result.get("status")
    if (
        status == "PostconditionFailed"
        and state.postcondition_called
        and _result_failed(state.result)
    ):
        if isinstance(state.result, dict):
            failure: dict[str, object] = {
                key: value
                for key, value in state.result.items()
                if isinstance(key, str)
            }
            failure.setdefault("committed", False)
            failure.setdefault("rollback_succeeded", True)
            failure.setdefault("rollback_failed", False)
            return failure
        return state.result
    if (
        status != "Committed"
        or native_result.get("committed") is not True
        or state.result is _MISSING_BODY_RESULT
    ):
        return _native_rejection(native_result)
    if not state.postcondition_called:
        return {
            "success": False,
            "ok": False,
            "error_code": "NATIVE_POSTCONDITION_NOT_RUN",
            "error": "Native runtime committed without running the postcondition",
            "committed": True,
            "outcome": "uncertain",
            "retry_safe": False,
        }
    return state.result


def run_body_native_mutation(
    collaborators: BodyCreateCollaborators,
    document_name: DocumentName,
    apply: Callable[[BodyDocument], object],
    postcondition: Callable[[BodyReadDocument], object],
) -> object:
    """Run the Body-only typed path through the required native boundary.

    The fixed policy is intentional: Body creation is structural, both
    callbacks receive the native-admitted document, recompute is native-owned,
    and a compatibility fallback is forbidden.
    """

    state = _NativeBodyMutationState()

    def native_apply(document: BodyDocument) -> object:
        state.document = document
        state.result = apply(document)
        if _result_failed(state.result):
            raise _CadMutationRollback
        return state.result

    def native_postcondition(document: BodyReadDocument) -> bool:
        state.postcondition_called = True
        if state.document is not document:
            state.result = {
                "success": False,
                "ok": False,
                "error_code": "DOCUMENT_IDENTITY_MISMATCH",
                "error": "Native mutation callbacks received different documents",
            }
            return False
        try:
            state.result = postcondition(document)
        except Exception as exc:
            state.result = {
                "success": False,
                "ok": False,
                "error_code": "CAD_POSTCONDITION_FAILED",
                "error": str(exc),
            }
            return False
        if _result_failed(state.result):
            return False
        try:
            collaborators.validate_document_invariants(document)
        except Exception as exc:
            state.result = {
                "success": False,
                "ok": False,
                "error_code": "DOCUMENT_HEALTH_DEGRADED",
                "error": str(exc),
            }
            return False
        return True

    try:
        native_result = collaborators.commit_body_create_mutation(
            document_name,
            native_apply,
            native_postcondition,
        )
    except LookupError:
        return {
            "success": False,
            "ok": False,
            "error_code": "DOCUMENT_NOT_FOUND",
            "error": f"Document {document_name!r} not found",
            "committed": False,
            "outcome": "rejected",
            "retry_safe": True,
        }
    except _CadMutationRollback:
        return state.result

    return _body_native_result(native_result, state)


def _make_legacy_native_callback(
    collaborators: Any,
    captured: dict[str, Any],
    callback: Callable[..., Any],
    document: Any,
    *,
    postcondition: Callable[..., Any] | None,
    bind_document: bool,
) -> Callable[[], Any]:
    def native_callback() -> Any:
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

    return native_callback


def _run_legacy_cad_mutation(
    collaborators: Any,
    document_name: str,
    callback: Callable[..., Any],
    *,
    structural: bool,
    postcondition: Callable[..., Any] | None,
    bind_document: bool,
) -> Any:
    document, lookup_error, lookup_available = _lookup_document(
        collaborators, document_name
    )
    if lookup_error is not None:
        return lookup_error
    if lookup_available and document is None:
        return _invoke_bound(callback, document, bind_document)

    captured: dict[str, Any] = {}
    native_callback = _make_legacy_native_callback(
        collaborators,
        captured,
        callback,
        document,
        postcondition=postcondition,
        bind_document=bind_document,
    )
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


def run_cad_mutation(
    collaborators: Any,
    document_name: str,
    callback: Callable[..., Any],
    *,
    structural: bool = False,
    postcondition: Callable[..., Any] | None = None,
    bind_document: bool = False,
    native_recompute: bool = False,
    require_native: bool = False,
) -> Any:
    """Run one typed CAD callback through one native compatibility commit.

    The native result is an internal attribution result.  The RPC caller keeps
    receiving the historical CAD callback envelope.  Failure-shaped legacy
    values escape through a private exception so the native coordinator rolls
    back before the original value is restored. ``bind_document`` passes the
    exact document resolved here to the apply and inspection callbacks. An
    explicitly opted-in ``native_recompute`` operation moves inspection and
    validation into the native post-recompute phase.
    """

    if postcondition is not None and not callable(postcondition):
        raise TypeError("postcondition must be callable")

    if native_recompute:
        return _run_native_recompute_mutation(
            collaborators,
            document_name,
            callback,
            structural=structural,
            postcondition=postcondition,
            bind_document=bind_document,
            require_native=require_native,
        )
    return _run_legacy_cad_mutation(
        collaborators,
        document_name,
        callback,
        structural=structural,
        postcondition=postcondition,
        bind_document=bind_document,
    )


__all__ = ["run_body_native_mutation", "run_cad_mutation"]
