"""Fixed native transaction policy for the typed ``export_brep`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

from ...._shared.protocol.export_brep_contract import (
    ExportBrepCollaborators,
    ExportBrepFailure,
    ExportBrepUncertain,
    DocumentName,
    MutationDocument,
    MutationReadDocument,
    make_export_brep_failure,
    make_export_brep_uncertain,
)
from .typed_runtime import TypedMutationError


class ExportBrepError(TypedMutationError):
    """An operation failure whose code survives a confirmed native rollback."""


class _AbortMutation(RuntimeError):
    """Ask the native coordinator to roll back a failed apply callback."""


@dataclass(slots=True)
class _NativeMutationState:
    document: object | None = None
    failure: TypedMutationError | None = None
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


def _export_brep_native_result(
    native_result: object, state: _NativeMutationState
) -> Literal[True] | ExportBrepFailure | ExportBrepUncertain:
    if not isinstance(native_result, dict):
        return make_export_brep_uncertain(
            "INVALID_NATIVE_EXPORT_BREP_RESULT",
            "Native commit returned no terminal result",
            committed=None,
        )
    status_value = native_result.get("status")
    status = status_value if isinstance(status_value, str) else None
    message_value = native_result.get("message")
    message = message_value if isinstance(message_value, str) else "Native export_brep mutation failed"
    committed = native_result.get("committed")
    if any(
        key in native_result and not isinstance(native_result[key], bool)
        for key in ("rollback_failed", "rollback_succeeded")
    ):
        return make_export_brep_uncertain(
            "INVALID_NATIVE_EXPORT_BREP_RESULT",
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
        return make_export_brep_uncertain(
            "EXPORT_BREP_ROLLBACK_UNCERTAIN",
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
        return make_export_brep_uncertain(
            "EXPORT_BREP_COMMITTED_RESPONSE_INVALID",
            "Native commit completed without a successful export_brep postcondition",
            committed=True,
            native_status=status,
        )
    if committed is not False or status not in _REJECTED_STATUSES:
        return make_export_brep_uncertain(
            "INVALID_NATIVE_EXPORT_BREP_RESULT",
            message,
            committed=True if committed is True or status == "Committed" else None,
            native_status=status,
            native_message=message,
        )
    failure = state.failure if status in {"ApplyFailed", "PostconditionFailed"} else None
    rolled_back = status in _ROLLED_BACK_STATUSES
    return make_export_brep_failure(
        failure.code if failure else "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        str(failure) if failure else message,
        native_status=status,
        native_message=message,
        rollback_succeeded=True if rolled_back else None,
        rollback_failed=False if rolled_back else None,
    )


def run_export_brep_native_mutation(
    collaborators: ExportBrepCollaborators,
    document_name: DocumentName,
    apply: Callable[[MutationDocument], None],
    postcondition: Callable[[MutationReadDocument], None],
) -> Literal[True] | ExportBrepFailure | ExportBrepUncertain:
    """Apply, recompute, inspect and validate on the same admitted document."""

    state = _NativeMutationState()

    def native_apply(document: object) -> None:
        state.document = document
        try:
            apply(cast(MutationDocument, document))
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, TypedMutationError)
                else ExportBrepError("EXPORT_BREP_FAILED", str(exc) or type(exc).__name__)
            )
            raise _AbortMutation from exc

    def native_postcondition(document: object) -> bool:
        if state.document is not document or state.failure is not None:
            state.failure = ExportBrepError(
                "DOCUMENT_IDENTITY_MISMATCH",
                "Native mutation callbacks did not receive the same admitted document",
            )
            return False
        try:
            postcondition(cast(MutationReadDocument, document))
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, TypedMutationError)
                else ExportBrepError("EXPORT_BREP_RESULT_FAILED", str(exc) or type(exc).__name__)
            )
            return False
        try:
            collaborators.validate_document_invariants(cast(MutationReadDocument, document))
        except Exception as exc:
            state.failure = ExportBrepError(
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
            return make_export_brep_failure(
                "DOCUMENT_NOT_FOUND",
                f"Document {document_name!r} not found",
            )
        return make_export_brep_uncertain(
            "EXPORT_BREP_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    except Exception as exc:
        return make_export_brep_uncertain(
            "EXPORT_BREP_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    return _export_brep_native_result(native_result, state)
