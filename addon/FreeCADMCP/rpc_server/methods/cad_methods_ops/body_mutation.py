"""Fixed native transaction policy for the reference Body mutation.

Callback results are provisional. Only a recognized native terminal status can
prove commit or rollback; exceptions and unknown statuses remain uncertain.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

try:
    from ...._shared.protocol.body_create_contract import (
        BodyCreateCollaborators,
        BodyCreateFailure,
        BodyCreateUncertain,
        BodyDocument,
        BodyReadDocument,
        DocumentName,
        make_body_create_failure,
        make_body_create_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.body_create_contract import (
        BodyCreateCollaborators,
        BodyCreateFailure,
        BodyCreateUncertain,
        BodyDocument,
        BodyReadDocument,
        DocumentName,
        make_body_create_failure,
        make_body_create_uncertain,
    )


class BodyCreateError(RuntimeError):
    """An operation failure whose code survives a confirmed native rollback."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _AbortBodyMutation(RuntimeError):
    """Ask the native coordinator to roll back a failed apply callback."""


@dataclass(slots=True)
class _NativeBodyMutationState:
    document: BodyDocument | None = None
    failure: BodyCreateError | None = None
    postcondition_passed: bool = False


# These native statuses prove that the model was never changed, or that native
# rollback succeeded. RollbackFailed replaces the original status on failure.
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


def _body_native_result(
    native_result: object, state: _NativeBodyMutationState
) -> Literal[True] | BodyCreateFailure | BodyCreateUncertain:
    if not isinstance(native_result, dict):
        return make_body_create_uncertain(
            "INVALID_NATIVE_BODY_RESULT",
            "Native commit returned no terminal result",
            committed=None,
        )
    status_value = native_result.get("status")
    status = status_value if isinstance(status_value, str) else None
    message_value = native_result.get("message")
    message = message_value if isinstance(message_value, str) else "Native Body mutation failed"
    committed = native_result.get("committed")
    if any(
        key in native_result and not isinstance(native_result[key], bool)
        for key in ("rollback_failed", "rollback_succeeded")
    ):
        return make_body_create_uncertain(
            "INVALID_NATIVE_BODY_RESULT",
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
        return make_body_create_uncertain(
            "BODY_CREATE_ROLLBACK_UNCERTAIN",
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
        return make_body_create_uncertain(
            "BODY_CREATE_COMMITTED_RESPONSE_INVALID",
            "Native commit completed without a successful Body postcondition",
            committed=True,
            native_status=status,
        )
    if committed is not False or status not in _REJECTED_STATUSES:
        return make_body_create_uncertain(
            "INVALID_NATIVE_BODY_RESULT",
            message,
            committed=True if committed is True or status == "Committed" else None,
            native_status=status,
            native_message=message,
        )
    failure = state.failure if status in {"ApplyFailed", "PostconditionFailed"} else None
    rolled_back = status in _ROLLED_BACK_STATUSES
    return make_body_create_failure(
        failure.code if failure else "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        str(failure) if failure else message,
        native_status=status,
        native_message=message,
        rollback_succeeded=True if rolled_back else None,
        rollback_failed=False if rolled_back else None,
    )


def run_body_native_mutation(
    collaborators: BodyCreateCollaborators,
    document_name: DocumentName,
    apply: Callable[[BodyDocument], None],
    postcondition: Callable[[BodyReadDocument], None],
) -> Literal[True] | BodyCreateFailure | BodyCreateUncertain:
    """Apply, recompute, inspect and validate on the same admitted document."""

    state = _NativeBodyMutationState()

    def native_apply(document: BodyDocument) -> None:
        state.document = document
        try:
            apply(document)
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, BodyCreateError)
                else BodyCreateError("BODY_CREATE_FAILED", str(exc) or type(exc).__name__)
            )
            raise _AbortBodyMutation from exc

    def native_postcondition(document: BodyReadDocument) -> bool:
        if state.document is not document or state.failure is not None:
            state.failure = BodyCreateError(
                "DOCUMENT_IDENTITY_MISMATCH",
                "Native mutation callbacks did not receive the same admitted document",
            )
            return False
        try:
            postcondition(document)
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, BodyCreateError)
                else BodyCreateError("BODY_CREATE_RESULT_FAILED", str(exc) or type(exc).__name__)
            )
            return False
        try:
            collaborators.validate_document_invariants(document)
        except Exception as exc:
            state.failure = BodyCreateError(
                "DOCUMENT_HEALTH_DEGRADED",
                str(exc) or type(exc).__name__,
            )
            return False
        state.postcondition_passed = True
        return True

    try:
        native_result = collaborators.commit_body_create_mutation(
            document_name,
            native_apply,
            native_postcondition,
        )
    except LookupError as exc:
        if state.document is None:
            return make_body_create_failure(
                "DOCUMENT_NOT_FOUND",
                f"Document {document_name!r} not found",
            )
        return make_body_create_uncertain(
            "BODY_CREATE_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    except Exception as exc:
        return make_body_create_uncertain(
            "BODY_CREATE_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    return _body_native_result(native_result, state)
