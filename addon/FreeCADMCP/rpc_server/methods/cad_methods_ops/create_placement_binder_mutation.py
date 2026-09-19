"""Fixed native transaction policy for the ``create_placement_binder`` mutation.

Callback results are provisional. Only a recognized native terminal status can
prove commit or rollback; exceptions and unknown statuses remain uncertain.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

try:
    from ...._shared.protocol.create_placement_binder_contract import (
        CreatePlacementBinderCollaborators,
        CreatePlacementBinderDocument,
        CreatePlacementBinderFailure,
        CreatePlacementBinderReadDocument,
        CreatePlacementBinderUncertain,
        DocumentName,
        make_create_placement_binder_failure,
        make_create_placement_binder_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.create_placement_binder_contract import (
        CreatePlacementBinderCollaborators,
        CreatePlacementBinderDocument,
        CreatePlacementBinderFailure,
        CreatePlacementBinderReadDocument,
        CreatePlacementBinderUncertain,
        DocumentName,
        make_create_placement_binder_failure,
        make_create_placement_binder_uncertain,
    )


class CreatePlacementBinderError(RuntimeError):
    """An operation failure whose code survives a confirmed native rollback."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _AbortMutation(RuntimeError):
    """Ask the native coordinator to roll back a failed apply callback."""


@dataclass(slots=True)
class _NativeMutationState:
    document: CreatePlacementBinderDocument | None = None
    failure: CreatePlacementBinderError | None = None
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


def _create_placement_binder_native_result(
    native_result: object, state: _NativeMutationState
) -> Literal[True] | CreatePlacementBinderFailure | CreatePlacementBinderUncertain:
    if not isinstance(native_result, dict):
        return make_create_placement_binder_uncertain(
            "INVALID_NATIVE_CREATE_PLACEMENT_BINDER_RESULT",
            "Native commit returned no terminal result",
            committed=None,
        )
    status_value = native_result.get("status")
    status = status_value if isinstance(status_value, str) else None
    message_value = native_result.get("message")
    message = message_value if isinstance(message_value, str) else "Native create_placement_binder mutation failed"
    committed = native_result.get("committed")
    if any(
        key in native_result and not isinstance(native_result[key], bool)
        for key in ("rollback_failed", "rollback_succeeded")
    ):
        return make_create_placement_binder_uncertain(
            "INVALID_NATIVE_CREATE_PLACEMENT_BINDER_RESULT",
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
        return make_create_placement_binder_uncertain(
            "CREATE_PLACEMENT_BINDER_ROLLBACK_UNCERTAIN",
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
        return make_create_placement_binder_uncertain(
            "CREATE_PLACEMENT_BINDER_COMMITTED_RESPONSE_INVALID",
            "Native commit completed without a successful postcondition",
            committed=True,
            native_status=status,
        )
    if committed is not False or status not in _REJECTED_STATUSES:
        return make_create_placement_binder_uncertain(
            "INVALID_NATIVE_CREATE_PLACEMENT_BINDER_RESULT",
            message,
            committed=True if committed is True or status == "Committed" else None,
            native_status=status,
            native_message=message,
        )
    failure = state.failure if status in {"ApplyFailed", "PostconditionFailed"} else None
    rolled_back = status in _ROLLED_BACK_STATUSES
    return make_create_placement_binder_failure(
        failure.code if failure else "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        str(failure) if failure else message,
        native_status=status,
        native_message=message,
        rollback_succeeded=True if rolled_back else None,
        rollback_failed=False if rolled_back else None,
    )


def run_create_placement_binder_native_mutation(
    collaborators: CreatePlacementBinderCollaborators,
    document_name: DocumentName,
    apply: Callable[[CreatePlacementBinderDocument], None],
    postcondition: Callable[[CreatePlacementBinderReadDocument], None],
) -> Literal[True] | CreatePlacementBinderFailure | CreatePlacementBinderUncertain:
    """Apply, recompute, inspect and validate on the same admitted document."""

    state = _NativeMutationState()

    def native_apply(document: object) -> None:
        typed = cast(CreatePlacementBinderDocument, document)
        state.document = typed
        try:
            apply(typed)
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, CreatePlacementBinderError)
                else CreatePlacementBinderError("CREATE_PLACEMENT_BINDER_FAILED", str(exc) or type(exc).__name__)
            )
            raise _AbortMutation from exc

    def native_postcondition(document: object) -> bool:
        typed = cast(CreatePlacementBinderReadDocument, document)
        if state.document is not typed or state.failure is not None:
            state.failure = CreatePlacementBinderError(
                "DOCUMENT_IDENTITY_MISMATCH",
                "Native mutation callbacks did not receive the same admitted document",
            )
            return False
        try:
            postcondition(typed)
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, CreatePlacementBinderError)
                else CreatePlacementBinderError("CREATE_PLACEMENT_BINDER_RESULT_FAILED", str(exc) or type(exc).__name__)
            )
            return False
        try:
            collaborators.validate_document_invariants(typed)
        except Exception as exc:
            state.failure = CreatePlacementBinderError(
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
            return make_create_placement_binder_failure(
                "DOCUMENT_NOT_FOUND",
                f"Document {document_name!r} not found",
            )
        return make_create_placement_binder_uncertain(
            "CREATE_PLACEMENT_BINDER_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    except Exception as exc:
        return make_create_placement_binder_uncertain(
            "CREATE_PLACEMENT_BINDER_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    return _create_placement_binder_native_result(native_result, state)
