"""Fixed native transaction policy for the ``capture_state`` mutation.

Callback results are provisional. Only a recognized native terminal status can
prove commit or rollback; exceptions and unknown statuses remain uncertain.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

from ...._shared.protocol.capture_state_contract import (
    CaptureStateCollaborators,
    CaptureStateDocument,
    CaptureStateFailure,
    CaptureStateReadDocument,
    CaptureStateUncertain,
    DocumentName,
    make_capture_state_failure,
    make_capture_state_uncertain,
)


class CaptureStateError(RuntimeError):
    """An operation failure whose code survives a confirmed native rollback."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _AbortMutation(RuntimeError):
    """Ask the native coordinator to roll back a failed apply callback."""


@dataclass(slots=True)
class _NativeMutationState:
    document: CaptureStateDocument | None = None
    failure: CaptureStateError | None = None
    postcondition_passed: bool = False


_REJECTED_STATUSES = frozenset(
    {
        "StaleDocument",
        "InvalidPreparedEdit",
        "Conflict",
        "Cancelled",
        "Unsupported",
        "Busy",
        "ApplyFailed",
        "RecomputeFailed",
        "PostconditionFailed",
        "PublicationFailed",
    }
)
_ROLLED_BACK_STATUSES = frozenset(
    {
        "ApplyFailed",
        "RecomputeFailed",
        "PostconditionFailed",
        "PublicationFailed",
    }
)


def _capture_state_native_result(
    native_result: object, state: _NativeMutationState
) -> Literal[True] | CaptureStateFailure | CaptureStateUncertain:
    if not isinstance(native_result, dict):
        return make_capture_state_uncertain(
            "INVALID_NATIVE_CAPTURE_STATE_RESULT",
            "Native commit returned no terminal result",
            committed=None,
        )
    status_value = native_result.get("status")
    status = status_value if isinstance(status_value, str) else None
    message_value = native_result.get("message")
    message = message_value if isinstance(message_value, str) else "Native capture_state mutation failed"
    committed = native_result.get("committed")
    if any(
        key in native_result and not isinstance(native_result[key], bool)
        for key in ("rollback_failed", "rollback_succeeded")
    ):
        return make_capture_state_uncertain(
            "INVALID_NATIVE_CAPTURE_STATE_RESULT",
            "Native rollback evidence has an invalid type",
            committed=True if committed is True else None,
            native_status=status,
        )
    rollback_failed = (
        status == "RollbackFailed"
        or native_result.get("rollback_failed") is True
        or native_result.get("rollback_succeeded") is False
    )
    if rollback_failed:
        return make_capture_state_uncertain(
            "CAPTURE_STATE_ROLLBACK_UNCERTAIN",
            message,
            committed=True if committed is True else None,
            native_status=status,
            native_message=message,
            rollback_succeeded=False,
            rollback_failed=True,
        )
    if status == "Committed" and committed is True and "rollback_succeeded" not in native_result:
        if state.postcondition_passed and state.failure is None:
            return True
        return make_capture_state_uncertain(
            "CAPTURE_STATE_COMMITTED_RESPONSE_INVALID",
            "Native commit completed without a successful postcondition",
            committed=True,
            native_status=status,
        )
    if committed is not False or status not in _REJECTED_STATUSES:
        return make_capture_state_uncertain(
            "INVALID_NATIVE_CAPTURE_STATE_RESULT",
            message,
            committed=True if committed is True or status == "Committed" else None,
            native_status=status,
            native_message=message,
        )
    failure = state.failure if status in {"ApplyFailed", "PostconditionFailed"} else None
    rolled_back = status in _ROLLED_BACK_STATUSES
    return make_capture_state_failure(
        failure.code if failure else "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        str(failure) if failure else message,
        native_status=status,
        native_message=message,
        rollback_succeeded=True if rolled_back else None,
        rollback_failed=False if rolled_back else None,
    )


def run_capture_state_native_mutation(
    collaborators: CaptureStateCollaborators,
    document_name: DocumentName,
    apply: Callable[[CaptureStateDocument], None],
    postcondition: Callable[[CaptureStateReadDocument], None],
) -> Literal[True] | CaptureStateFailure | CaptureStateUncertain:
    """Apply, recompute, inspect and validate on the same admitted document."""

    state = _NativeMutationState()

    def native_apply(document: object) -> None:
        typed = cast(CaptureStateDocument, document)
        state.document = typed
        try:
            apply(typed)
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, CaptureStateError)
                else CaptureStateError("CAPTURE_STATE_FAILED", str(exc) or type(exc).__name__)
            )
            raise _AbortMutation from exc

    def native_postcondition(document: object) -> bool:
        typed = cast(CaptureStateReadDocument, document)
        if state.document is not typed or state.failure is not None:
            state.failure = CaptureStateError(
                "DOCUMENT_IDENTITY_MISMATCH",
                "Native mutation callbacks did not receive the same admitted document",
            )
            return False
        try:
            postcondition(typed)
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, CaptureStateError)
                else CaptureStateError("CAPTURE_STATE_RESULT_FAILED", str(exc) or type(exc).__name__)
            )
            return False
        try:
            collaborators.validate_document_invariants(typed)
        except Exception as exc:
            state.failure = CaptureStateError(
                "DOCUMENT_HEALTH_DEGRADED",
                str(exc) or type(exc).__name__,
            )
            return False
        state.postcondition_passed = True
        return True

    try:
        native_result = collaborators.commit_native_mutation(
            document_name,
            native_apply,
            native_postcondition,
            structural=False,
        )
    except LookupError as exc:
        if state.document is None:
            return make_capture_state_failure(
                "DOCUMENT_NOT_FOUND",
                f"Document {document_name!r} not found",
            )
        return make_capture_state_uncertain(
            "CAPTURE_STATE_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    except Exception as exc:
        return make_capture_state_uncertain(
            "CAPTURE_STATE_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    return _capture_state_native_result(native_result, state)
