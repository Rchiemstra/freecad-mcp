"""Fixed native transaction policy for the typed ``sketch_delete_geometry`` mutation.

Callback results are provisional. Only a recognized native terminal status can
prove commit or rollback; exceptions and unknown statuses remain uncertain.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

from ...._shared.protocol.sketch_delete_geometry_contract import (
    SketchDeleteGeometryCollaborators,
    SketchDeleteGeometryDocument,
    SketchDeleteGeometryFailure,
    SketchDeleteGeometryReadDocument,
    SketchDeleteGeometryUncertain,
    make_sketch_delete_geometry_failure,
    make_sketch_delete_geometry_uncertain,
)


class SketchDeleteGeometryError(RuntimeError):
    """An operation failure whose code survives a confirmed native rollback."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _AbortSketchDeleteGeometryMutation(RuntimeError):
    """Ask the native coordinator to roll back a failed apply callback."""


@dataclass(slots=True)
class _NativeSketchDeleteGeometryMutationState:
    document: object | None = None
    failure: SketchDeleteGeometryError | None = None
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


def _sketch_delete_geometry_native_result(
    native_result: object, state: _NativeSketchDeleteGeometryMutationState
) -> Literal[True] | SketchDeleteGeometryFailure | SketchDeleteGeometryUncertain:
    if not isinstance(native_result, dict):
        return make_sketch_delete_geometry_uncertain(
            "INVALID_NATIVE_SKETCH_DELETE_GEOMETRY_RESULT",
            "Native commit returned no terminal result",
            committed=None,
        )
    status_value = native_result.get("status")
    status = status_value if isinstance(status_value, str) else None
    message_value = native_result.get("message")
    message = message_value if isinstance(message_value, str) else "Native sketch_delete_geometry mutation failed"
    committed = native_result.get("committed")
    if any(
        key in native_result and not isinstance(native_result[key], bool)
        for key in ("rollback_failed", "rollback_succeeded")
    ):
        return make_sketch_delete_geometry_uncertain(
            "INVALID_NATIVE_SKETCH_DELETE_GEOMETRY_RESULT",
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
        return make_sketch_delete_geometry_uncertain(
            "SKETCH_DELETE_GEOMETRY_ROLLBACK_UNCERTAIN",
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
        return make_sketch_delete_geometry_uncertain(
            "SKETCH_DELETE_GEOMETRY_COMMITTED_RESPONSE_INVALID",
            "Native commit completed without a successful sketch_delete_geometry postcondition",
            committed=True,
            native_status=status,
        )
    if committed is not False or status not in _REJECTED_STATUSES:
        return make_sketch_delete_geometry_uncertain(
            "INVALID_NATIVE_SKETCH_DELETE_GEOMETRY_RESULT",
            message,
            committed=True if committed is True or status == "Committed" else None,
            native_status=status,
            native_message=message,
        )
    failure = state.failure if status in {"ApplyFailed", "PostconditionFailed"} else None
    rolled_back = status in _ROLLED_BACK_STATUSES
    return make_sketch_delete_geometry_failure(
        failure.code if failure else "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        str(failure) if failure else message,
        native_status=status,
        native_message=message,
        rollback_succeeded=True if rolled_back else None,
        rollback_failed=False if rolled_back else None,
    )


def run_sketch_delete_geometry_native_mutation(
    collaborators: SketchDeleteGeometryCollaborators,
    document_name: str,
    apply: Callable[[SketchDeleteGeometryDocument], None],
    postcondition: Callable[[SketchDeleteGeometryReadDocument], None],
) -> Literal[True] | SketchDeleteGeometryFailure | SketchDeleteGeometryUncertain:
    """Apply, recompute, inspect and validate on the same admitted document."""

    state = _NativeSketchDeleteGeometryMutationState()

    def native_apply(document: object) -> None:
        state.document = document
        try:
            apply(cast(SketchDeleteGeometryDocument, document))
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, SketchDeleteGeometryError)
                else SketchDeleteGeometryError("SKETCH_DELETE_GEOMETRY_FAILED", str(exc) or type(exc).__name__)
            )
            raise _AbortSketchDeleteGeometryMutation from exc

    def native_postcondition(document: object) -> bool:
        if state.document is not document or state.failure is not None:
            state.failure = SketchDeleteGeometryError(
                "DOCUMENT_IDENTITY_MISMATCH",
                "Native mutation callbacks did not receive the same admitted document",
            )
            return False
        admitted = cast(SketchDeleteGeometryReadDocument, document)
        try:
            postcondition(admitted)
        except Exception as exc:
            state.failure = (
                exc
                if isinstance(exc, SketchDeleteGeometryError)
                else SketchDeleteGeometryError("SKETCH_DELETE_GEOMETRY_RESULT_FAILED", str(exc) or type(exc).__name__)
            )
            return False
        try:
            collaborators.validate_document_invariants(admitted)
        except Exception as exc:
            state.failure = SketchDeleteGeometryError(
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
            return make_sketch_delete_geometry_failure(
                "DOCUMENT_NOT_FOUND",
                f"Document {document_name!r} not found",
            )
        return make_sketch_delete_geometry_uncertain(
            "SKETCH_DELETE_GEOMETRY_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    except Exception as exc:
        return make_sketch_delete_geometry_uncertain(
            "SKETCH_DELETE_GEOMETRY_NATIVE_EXCEPTION",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    return _sketch_delete_geometry_native_result(native_result, state)
