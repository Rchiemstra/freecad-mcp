"""Document lease service operations — save cancel."""

from __future__ import annotations

from dataclasses import replace

from ..errors.cancellation_context import _CancellationContext
from ..errors.coordination_error import CoordinationError
from ..errors.lease_service_error import LeaseServiceError
from ..errors.lease_state_error import LeaseStateError
from ..model import (
    LeaseCredential,
    LeaseErrorInfo,
    LeaseRecord,
    LeaseState,
)
from ..sidecar import (
    SidecarError,
)
from .constants import (
    bounded_text,
)


def begin_save(self, credential: LeaseCredential) -> LeaseRecord:
    with self._lock:
        record = self._record_for_credential(
            credential,
            allowed_states={LeaseState.LOCKED_IDLE, LeaseState.LOCKED_ERROR},
        )
        updated = record.transitioned(
            LeaseState.LOCKED_SAVING,
            current_operation="Saving and verifying",
        )
        return self._commit(record, updated)


def cancel_save_before_mutation(self, credential: LeaseCredential) -> LeaseRecord:
    """Return a preflight-only Save As conflict to idle without hiding writes."""

    with self._lock:
        record = self._record_for_credential(
            credential, allowed_states={LeaseState.LOCKED_SAVING}
        )
        pending = self._pending_save_as.get(credential.document_session_uuid)
        if pending is not None:
            path = self._sidecar_path(pending)
            if path is not None:
                try:
                    self.sidecar_store.delete(path, expected=pending)
                except SidecarError as exc:
                    raise CoordinationError(
                        f"unable to remove Save As reservation: {exc}"
                    ) from exc
            self._pending_save_as.pop(credential.document_session_uuid, None)
        updated = record.transitioned(
            LeaseState.LOCKED_IDLE,
            current_operation="",
            migration=None,
        )
        return self._commit(record, updated)


def begin_cancellation(
    self,
    credential: LeaseCredential,
    *,
    request_id: str,
    operation: str = "Cancelling request",
    mutation_may_have_begun: bool = False,
) -> LeaseRecord:
    """Fence new writes while an authenticated request is being cancelled.

    This is a typed service event, not a caller-selected state transition.
    Repeating it for the same request is idempotent; a different request
    may not take over an in-progress cancellation.
    """

    request_id = bounded_text(request_id, 64)
    if not request_id:
        raise LeaseServiceError("cancellation request_id is required")
    session_uuid = credential.document_session_uuid
    with self._lock:
        record = self._record_for_credential(
            credential,
            allowed_states={
                LeaseState.LOCKED_IDLE,
                LeaseState.LOCKED_EDITING,
                LeaseState.LOCKED_RECOMPUTING,
                LeaseState.LOCKED_SAVING,
                LeaseState.LOCKED_ERROR,
                LeaseState.CANCELLING,
            },
        )
        existing = self._cancellations.get(session_uuid)
        if record.state == LeaseState.CANCELLING:
            if existing is None or existing.request_id != request_id:
                raise LeaseStateError(
                    "document is already cancelling a different request"
                )
            if mutation_may_have_begun and not existing.mutation_may_have_begun:
                self._cancellations[session_uuid] = replace(
                    existing, mutation_may_have_begun=True
                )
            return record
        if record.state not in {
            LeaseState.LOCKED_IDLE,
            LeaseState.LOCKED_EDITING,
            LeaseState.LOCKED_RECOMPUTING,
            LeaseState.LOCKED_SAVING,
            LeaseState.LOCKED_ERROR,
        }:
            raise LeaseStateError(
                f"request cancellation is forbidden in {record.state.value}"
            )
        context = _CancellationContext(
            request_id=request_id,
            previous_state=record.state,
            previous_operation=record.current_operation,
            mutation_may_have_begun=bool(mutation_may_have_begun),
        )
        updated = record.transitioned(
            LeaseState.CANCELLING,
            current_operation=bounded_text(operation, 512),
        )
        committed = self._commit(record, updated)
        self._cancellations[session_uuid] = context
        return committed


def complete_cancellation(
    self,
    credential: LeaseCredential,
    *,
    request_id: str,
    mutation_may_have_begun: bool,
    dirty: bool | None = None,
    message: str = "authenticated request cancelled",
) -> LeaseRecord:
    """Resolve ``CANCELLING`` after queued/running work is known complete.

    An exact pre-save destination reservation is CAS-removed only when no
    FreeCAD mutation/save invocation began.  Any uncertainty or possible
    mutation becomes ``LOCKED_ERROR`` and deliberately retains recovery
    sidecars.
    """

    request_id = bounded_text(request_id, 64)
    session_uuid = credential.document_session_uuid
    with self._lock:
        record = self._record_for_credential(
            credential,
            allowed_states={
                LeaseState.CANCELLING,
                LeaseState.LOCKED_IDLE,
                LeaseState.LOCKED_ERROR,
            },
        )
        context = self._cancellations.get(session_uuid)
        if context is None:
            # Repeated completion after the first result is harmless.
            if record.state in {LeaseState.LOCKED_IDLE, LeaseState.LOCKED_ERROR}:
                return record
            raise LeaseStateError("document has no matching cancellation event")
        if context.request_id != request_id:
            raise LeaseStateError("cancellation completion request_id mismatch")
        if record.state != LeaseState.CANCELLING:
            raise LeaseStateError(
                f"cancellation completion is forbidden in {record.state.value}"
            )
        may_have_mutated = bool(
            mutation_may_have_begun or context.mutation_may_have_begun
        )
        if may_have_mutated:
            error = LeaseErrorInfo(
                code="REQUEST_CANCELLED_AFTER_MUTATION",
                message=bounded_text(message, 2048),
                at=self._utc_clock(),
                request_id=request_id,
            )
            updated = record.transitioned(
                LeaseState.LOCKED_ERROR,
                current_operation="",
                dirty=True if dirty is None else bool(dirty),
                validation_complete=False,
                error=error,
            )
            committed = self._commit(record, updated)
            self._cancellations.pop(session_uuid, None)
            return committed

        pending = self._pending_save_as.get(session_uuid)
        if pending is not None:
            path = self._sidecar_path(pending)
            if path is not None:
                try:
                    self.sidecar_store.delete(path, expected=pending)
                except SidecarError as exc:
                    error = LeaseErrorInfo(
                        code="CANCELLATION_ROLLBACK_FAILED",
                        message=bounded_text(str(exc), 2048),
                        at=self._utc_clock(),
                        request_id=request_id,
                    )
                    failed = record.transitioned(
                        LeaseState.LOCKED_ERROR,
                        dirty=bool(record.dirty),
                        validation_complete=False,
                        error=error,
                    )
                    self._commit(record, failed)
                    self._cancellations.pop(session_uuid, None)
                    raise CoordinationError(
                        f"unable to remove Save As reservation: {exc}"
                    ) from exc
            self._pending_save_as.pop(session_uuid, None)

        target = (
            LeaseState.LOCKED_ERROR
            if context.previous_state == LeaseState.LOCKED_ERROR
            else LeaseState.LOCKED_IDLE
        )
        updated = record.transitioned(
            target,
            current_operation=(
                context.previous_operation if target == LeaseState.LOCKED_ERROR else ""
            ),
            migration=None,
        )
        committed = self._commit(record, updated)
        self._cancellations.pop(session_uuid, None)
        return committed
