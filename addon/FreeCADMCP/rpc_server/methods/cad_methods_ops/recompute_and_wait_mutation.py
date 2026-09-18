"""Native transaction policy for the typed ``recompute_and_wait`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

try:
    from ...._shared.protocol.recompute_and_wait_contract import (
        RecomputeAndWaitCollaborators,
        RecomputeAndWaitReadDocument,
        RecomputeAndWaitFailure,
        RecomputeAndWaitUncertain,
        make_recompute_and_wait_failure,
        make_recompute_and_wait_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.recompute_and_wait_contract import (
        RecomputeAndWaitCollaborators,
        RecomputeAndWaitReadDocument,
        RecomputeAndWaitFailure,
        RecomputeAndWaitUncertain,
        make_recompute_and_wait_failure,
        make_recompute_and_wait_uncertain,
    )


class RecomputeAndWaitError(RuntimeError):
    """An operation failure whose code survives a confirmed native rollback."""

    def __init__(self, code: str, message: str, diagnostics: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


class _AbortMutation(RuntimeError):
    """Ask the native coordinator to roll back a failed apply callback."""


@dataclass(slots=True)
class _NativeMutationState:
    document: object | None = None
    failure: RecomputeAndWaitError | None = None
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


def _recompute_and_wait_native_result(
    native_result: object, state: _NativeMutationState
) -> Literal[True] | RecomputeAndWaitFailure | RecomputeAndWaitUncertain:
    if not isinstance(native_result, dict):
        return make_recompute_and_wait_uncertain(
            "INVALID_NATIVE_RECOMPUTE_AND_WAIT_RESULT",
            "Native commit returned no terminal result",
            committed=None,
        )
    status_value = native_result.get("status")
    status = status_value if isinstance(status_value, str) else None
    message_value = native_result.get("message")
    message = message_value if isinstance(message_value, str) else "Native recompute_and_wait mutation failed"
    committed = native_result.get("committed")
    if any(
        key in native_result and not isinstance(native_result[key], bool)
        for key in ("rollback_failed", "rollback_succeeded")
    ):
        return make_recompute_and_wait_uncertain(
            "INVALID_NATIVE_RECOMPUTE_AND_WAIT_RESULT",
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
        return make_recompute_and_wait_uncertain(
            "RECOMPUTE_AND_WAIT_ROLLBACK_UNCERTAIN",
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
        return make_recompute_and_wait_uncertain(
            "RECOMPUTE_AND_WAIT_COMMITTED_RESPONSE_INVALID",
            "Native commit completed without a successful recompute_and_wait postcondition",
            committed=True,
            native_status=status,
        )
    if committed is not False or status not in _REJECTED_STATUSES:
        return make_recompute_and_wait_uncertain(
            "INVALID_NATIVE_RECOMPUTE_AND_WAIT_RESULT",
            message,
            committed=True if committed is True or status == "Committed" else None,
            native_status=status,
            native_message=message,
        )
    failure = state.failure if status in {"ApplyFailed", "PostconditionFailed"} else None
    rolled_back = status in _ROLLED_BACK_STATUSES
    return make_recompute_and_wait_failure(
        failure.code if failure else "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        str(failure) if failure else message,
        native_status=status,
        native_message=message,
        rollback_succeeded=True if rolled_back else None,
        rollback_failed=False if rolled_back else None,
        diagnostics=None if failure is None else failure.diagnostics,
    )


def run_recompute_and_wait_native_mutation(
    collaborators: RecomputeAndWaitCollaborators,
    document_name: str,
    apply: Callable[[object], None],
    postcondition: Callable[[object], None],
) -> Literal[True] | RecomputeAndWaitFailure | RecomputeAndWaitUncertain:
    """Apply, recompute, inspect and validate on the same admitted document."""

    state = _NativeMutationState()

    def native_apply(document: object) -> None:
        state.document = document
        try:
            apply(document)
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, RecomputeAndWaitError)
                else RecomputeAndWaitError("RECOMPUTE_AND_WAIT_FAILED", str(exc) or type(exc).__name__)
            )
            raise _AbortMutation from exc

    def native_postcondition(document: object) -> bool:
        if state.document is not document or state.failure is not None:
            state.failure = RecomputeAndWaitError(
                "DOCUMENT_IDENTITY_MISMATCH",
                "Native mutation callbacks did not receive the same admitted document",
            )
            return False
        try:
            postcondition(document)
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, RecomputeAndWaitError)
                else RecomputeAndWaitError("RECOMPUTE_AND_WAIT_RESULT_FAILED", str(exc) or type(exc).__name__)
            )
            return False
        try:
            collaborators.validate_document_invariants(cast(RecomputeAndWaitReadDocument, document))
        except Exception as exc:
            state.failure = RecomputeAndWaitError(
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
            structural=True,
        )
    except LookupError as exc:
        if state.document is None:
            return make_recompute_and_wait_failure(
                "DOCUMENT_NOT_FOUND",
                f"Document {document_name!r} not found",
            )
        return make_recompute_and_wait_uncertain(
            "RECOMPUTE_AND_WAIT_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    except Exception as exc:
        return make_recompute_and_wait_uncertain(
            "RECOMPUTE_AND_WAIT_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    return _recompute_and_wait_native_result(native_result, state)
