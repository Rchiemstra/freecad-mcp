"""Document lease service operations — mutation ops."""

from __future__ import annotations

from typing import Any

from ..model import (
    LeaseCredential,
    LeaseErrorInfo,
    LeaseRecord,
    LeaseState,
)
from .constants import (
    bounded_text,
)


def begin_mutation(self, credential: LeaseCredential, *, operation: str) -> LeaseRecord:
    with self._lock:
        record = self._record_for_credential(
            credential, allowed_states={LeaseState.LOCKED_IDLE}
        )
        updated = record.transitioned(
            LeaseState.LOCKED_EDITING,
            current_operation=bounded_text(operation, 512),
            last_mutation_revision=record.last_mutation_revision + 1,
            validation_complete=False,
            error=None,
        )
        return self._commit(record, updated)


def begin_recovery(self, credential: LeaseCredential, *, operation: str) -> LeaseRecord:
    """Begin an explicitly classified recovery from ``LOCKED_ERROR``."""

    with self._lock:
        record = self._record_for_credential(
            credential, allowed_states={LeaseState.LOCKED_ERROR}
        )
        updated = record.transitioned(
            LeaseState.LOCKED_EDITING,
            current_operation=bounded_text(operation, 512),
            last_mutation_revision=record.last_mutation_revision + 1,
            validation_complete=False,
            error=None,
        )
        return self._commit(record, updated)


def begin_recompute(self, credential: LeaseCredential) -> LeaseRecord:
    with self._lock:
        record = self._record_for_credential(
            credential,
            allowed_states={LeaseState.LOCKED_IDLE, LeaseState.LOCKED_EDITING},
        )
        mutation_revision = record.last_mutation_revision
        if record.state == LeaseState.LOCKED_IDLE:
            mutation_revision += 1
        updated = record.transitioned(
            LeaseState.LOCKED_RECOMPUTING,
            current_operation="Recomputing",
            last_mutation_revision=mutation_revision,
            validation_complete=False,
        )
        return self._commit(record, updated)


def complete_operation(
    self, credential: LeaseCredential, *, dirty: bool
) -> LeaseRecord:
    with self._lock:
        record = self._record_for_credential(
            credential,
            allowed_states={
                LeaseState.LOCKED_EDITING,
                LeaseState.LOCKED_RECOMPUTING,
            },
        )
        updated = record.transitioned(
            LeaseState.LOCKED_IDLE,
            current_operation="",
            dirty=bool(dirty),
        )
        return self._commit(record, updated)


def record_error(
    self,
    credential: LeaseCredential,
    *,
    code: str,
    message: str,
    request_id: str | None = None,
    dirty: bool | None = None,
) -> LeaseRecord:
    with self._lock:
        record = self._record_for_credential(credential)
        error = LeaseErrorInfo(
            code=bounded_text(code, 128) or "UNKNOWN",
            message=bounded_text(message, 2048),
            at=self._utc_clock(),
            request_id=bounded_text(request_id, 64) or None,
        )
        changes: dict[str, Any] = {"error": error}
        if dirty is not None:
            changes["dirty"] = bool(dirty)
        if record.state == LeaseState.LOCKED_ERROR:
            updated = record.revised(**changes)
        else:
            updated = record.transitioned(LeaseState.LOCKED_ERROR, **changes)
        return self._commit(record, updated)
