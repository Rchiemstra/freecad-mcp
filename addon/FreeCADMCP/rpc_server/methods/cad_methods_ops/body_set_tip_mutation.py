"""Fixed native transaction policy for the typed Body Tip mutation.

Callback results are provisional. Only a recognized native terminal status can
prove commit or rollback; exceptions and unknown statuses remain uncertain.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

from ...._shared.protocol.body_set_tip_contract import (
    BodySetTipCollaborators,
    BodySetTipFailure,
    BodySetTipUncertain,
    DocumentName,
    TipBodyDocument,
    TipReadDocument,
    make_body_set_tip_failure,
    make_body_set_tip_uncertain,
)


class BodySetTipError(RuntimeError):
    """An operation failure whose code survives a confirmed native rollback."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _AbortTipMutation(RuntimeError):
    """Ask the native coordinator to roll back a failed apply callback."""


@dataclass(slots=True)
class _NativeTipMutationState:
    document: TipBodyDocument | None = None
    failure: BodySetTipError | None = None
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


def _tip_native_result(
    native_result: object, state: _NativeTipMutationState
) -> Literal[True] | BodySetTipFailure | BodySetTipUncertain:
    if not isinstance(native_result, dict):
        return make_body_set_tip_uncertain(
            "INVALID_NATIVE_BODY_SET_TIP_RESULT",
            "Native commit returned no terminal result",
            committed=None,
        )
    status_value = native_result.get("status")
    status = status_value if isinstance(status_value, str) else None
    message_value = native_result.get("message")
    message = (
        message_value if isinstance(message_value, str) else "Native Body Tip mutation failed"
    )
    committed = native_result.get("committed")
    if any(
        key in native_result and not isinstance(native_result[key], bool)
        for key in ("rollback_failed", "rollback_succeeded")
    ):
        return make_body_set_tip_uncertain(
            "INVALID_NATIVE_BODY_SET_TIP_RESULT",
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
        return make_body_set_tip_uncertain(
            "BODY_SET_TIP_ROLLBACK_UNCERTAIN",
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
        return make_body_set_tip_uncertain(
            "BODY_SET_TIP_COMMITTED_RESPONSE_INVALID",
            "Native commit completed without a successful Body Tip postcondition",
            committed=True,
            native_status=status,
        )
    if committed is not False or status not in _REJECTED_STATUSES:
        return make_body_set_tip_uncertain(
            "INVALID_NATIVE_BODY_SET_TIP_RESULT",
            message,
            committed=True if committed is True or status == "Committed" else None,
            native_status=status,
            native_message=message,
        )
    failure = state.failure if status in {"ApplyFailed", "PostconditionFailed"} else None
    rolled_back = status in _ROLLED_BACK_STATUSES
    return make_body_set_tip_failure(
        failure.code if failure else "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        str(failure) if failure else message,
        native_status=status,
        native_message=message,
        rollback_succeeded=True if rolled_back else None,
        rollback_failed=False if rolled_back else None,
    )


def run_body_set_tip_native_mutation(
    collaborators: BodySetTipCollaborators,
    document_name: DocumentName,
    apply: Callable[[TipBodyDocument], None],
    postcondition: Callable[[TipReadDocument], None],
) -> Literal[True] | BodySetTipFailure | BodySetTipUncertain:
    """Apply, recompute, inspect and validate on the same admitted document."""

    state = _NativeTipMutationState()

    def native_apply(document: object) -> object:
        admitted = cast(TipBodyDocument, document)
        state.document = admitted
        try:
            apply(admitted)
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, BodySetTipError)
                else BodySetTipError("BODY_SET_TIP_FAILED", str(exc) or type(exc).__name__)
            )
            raise _AbortTipMutation from exc
        return None

    def native_postcondition(document: object) -> object:
        admitted = cast(TipReadDocument, document)
        if state.document is not document or state.failure is not None:
            state.failure = BodySetTipError(
                "DOCUMENT_IDENTITY_MISMATCH",
                "Native mutation callbacks did not receive the same admitted document",
            )
            return False
        try:
            postcondition(admitted)
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, BodySetTipError)
                else BodySetTipError(
                    "BODY_SET_TIP_RESULT_FAILED", str(exc) or type(exc).__name__
                )
            )
            return False
        try:
            collaborators.validate_document_invariants(admitted)
        except Exception as exc:
            state.failure = BodySetTipError(
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
        )
    except LookupError as exc:
        if state.document is None:
            return make_body_set_tip_failure(
                "DOCUMENT_NOT_FOUND",
                f"Document {document_name!r} not found",
            )
        return make_body_set_tip_uncertain(
            "BODY_SET_TIP_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    except Exception as exc:
        return make_body_set_tip_uncertain(
            "BODY_SET_TIP_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    return _tip_native_result(native_result, state)
