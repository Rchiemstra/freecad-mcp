"""Fixed native transaction policy for the typed ``pocket_feature`` mutation.

Callback results are provisional. Only a recognized native terminal status can
prove commit or rollback; exceptions and unknown statuses remain uncertain.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

from ...._shared.protocol.pocket_feature_contract import (
    PocketFeatureCollaborators,
    PocketFeatureDocument,
    PocketFeatureFailure,
    PocketFeatureReadDocument,
    PocketFeatureUncertain,
    make_pocket_feature_failure,
    make_pocket_feature_uncertain,
)


class PocketFeatureError(RuntimeError):
    """An operation failure whose code survives a confirmed native rollback."""

    def __init__(
        self,
        code: str,
        message: str,
        diagnostics: dict[str, object] | None = None,
        fields: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics
        self.fields = fields or {}


class _AbortPocketFeatureMutation(RuntimeError):
    """Ask the native coordinator to roll back a failed apply callback."""


@dataclass(slots=True)
class _NativePocketFeatureMutationState:
    document: object | None = None
    failure: PocketFeatureError | None = None
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


def _pocket_feature_native_result(
    native_result: object, state: _NativePocketFeatureMutationState
) -> Literal[True] | PocketFeatureFailure | PocketFeatureUncertain:
    if not isinstance(native_result, dict):
        return make_pocket_feature_uncertain(
            "INVALID_NATIVE_POCKET_FEATURE_RESULT",
            "Native commit returned no terminal result",
            committed=None,
        )
    status_value = native_result.get("status")
    status = status_value if isinstance(status_value, str) else None
    message_value = native_result.get("message")
    message = message_value if isinstance(message_value, str) else "Native pocket_feature mutation failed"
    committed = native_result.get("committed")
    if any(
        key in native_result and not isinstance(native_result[key], bool)
        for key in ("rollback_failed", "rollback_succeeded")
    ):
        return make_pocket_feature_uncertain(
            "INVALID_NATIVE_POCKET_FEATURE_RESULT",
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
        return make_pocket_feature_uncertain(
            "POCKET_FEATURE_ROLLBACK_UNCERTAIN",
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
        return make_pocket_feature_uncertain(
            "POCKET_FEATURE_COMMITTED_RESPONSE_INVALID",
            "Native commit completed without a successful pocket_feature postcondition",
            committed=True,
            native_status=status,
        )
    if committed is not False or status not in _REJECTED_STATUSES:
        return make_pocket_feature_uncertain(
            "INVALID_NATIVE_POCKET_FEATURE_RESULT",
            message,
            committed=True if committed is True or status == "Committed" else None,
            native_status=status,
            native_message=message,
        )
    failure = state.failure if status in {"ApplyFailed", "PostconditionFailed"} else None
    rolled_back = status in _ROLLED_BACK_STATUSES
    result = make_pocket_feature_failure(
        failure.code if failure else "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        str(failure) if failure else message,
        native_status=status,
        native_message=message,
        rollback_succeeded=True if rolled_back else None,
        rollback_failed=False if rolled_back else None,
        diagnostics=failure.diagnostics if failure is not None else None,
    )
    if failure is not None:
        result.update(failure.fields)  # type: ignore[typeddict-item]
    return result


def run_pocket_feature_native_mutation(
    collaborators: PocketFeatureCollaborators,
    document_name: str,
    apply: Callable[[PocketFeatureDocument], None],
    postcondition: Callable[[PocketFeatureReadDocument], None],
) -> Literal[True] | PocketFeatureFailure | PocketFeatureUncertain:
    """Apply, recompute, inspect and validate on the same admitted document."""

    state = _NativePocketFeatureMutationState()

    def native_apply(document: object) -> None:
        state.document = document
        try:
            apply(cast(PocketFeatureDocument, document))
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, PocketFeatureError)
                else PocketFeatureError("POCKET_FEATURE_FAILED", str(exc) or type(exc).__name__)
            )
            raise _AbortPocketFeatureMutation from exc

    def native_postcondition(document: object) -> bool:
        if state.document is not document or state.failure is not None:
            state.failure = PocketFeatureError(
                "DOCUMENT_IDENTITY_MISMATCH",
                "Native mutation callbacks did not receive the same admitted document",
            )
            return False
        admitted = cast(PocketFeatureReadDocument, document)
        try:
            postcondition(admitted)
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, PocketFeatureError)
                else PocketFeatureError("POCKET_FEATURE_RESULT_FAILED", str(exc) or type(exc).__name__)
            )
            return False
        try:
            collaborators.validate_document_invariants(admitted)
        except Exception as exc:
            state.failure = PocketFeatureError(
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
            return make_pocket_feature_failure(
                "DOCUMENT_NOT_FOUND",
                f"Document {document_name!r} not found",
            )
        return make_pocket_feature_uncertain(
            "POCKET_FEATURE_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    except Exception as exc:
        return make_pocket_feature_uncertain(
            "POCKET_FEATURE_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    return _pocket_feature_native_result(native_result, state)
