"""Document lease service operations — authorize ops."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any

from ..model import (
    DocumentSelector,
    LeaseCredential,
    LeaseRecord,
    LeaseState,
)
from .constants import (
    OWNER_AUTHORIZABLE_STATES,
    bounded_diagnostic,
)


def authorize(
    self,
    credential: LeaseCredential,
    *,
    selector: DocumentSelector | Mapping[str, Any] | str | None = None,
    allowed_states: Iterable[LeaseState] = OWNER_AUTHORIZABLE_STATES,
) -> LeaseRecord:
    with self._lock:
        return self._record_for_credential(
            credential, allowed_states=allowed_states, selector=selector
        )


def heartbeat(
    self,
    credential: LeaseCredential,
    *,
    current_operation: str | None = None,
    task_summary: str | None = None,
) -> dict[str, Any]:
    """Renew liveness and diagnostic metadata; never accept a state/dirty value."""

    with self._lock:
        record = self._record_for_credential(credential)
        now_mono = self._monotonic_ns()
        changes: dict[str, Any] = {
            "last_heartbeat_at": self._utc_clock(),
            "monotonic_heartbeat_ns": now_mono,
            "heartbeat_sequence": record.heartbeat_sequence + 1,
        }
        if current_operation is not None:
            changes["current_operation"] = bounded_diagnostic(
                current_operation,
                512,
                secrets_to_remove=(credential.token,),
            )
        if task_summary is not None:
            changes["task_summary"] = bounded_diagnostic(
                task_summary,
                1024,
                secrets_to_remove=(credential.token,),
            )
        updated = replace(record, **changes)
        last_flush = self._last_sidecar_heartbeat_ns.get(
            credential.document_session_uuid, 0
        )
        if (
            self._sidecar_path(record) is not None
            and now_mono - last_flush >= self._sidecar_heartbeat_ns
        ):
            updated = replace(updated, record_revision=record.record_revision + 1)
            self._commit(record, updated)
            self._last_sidecar_heartbeat_ns[credential.document_session_uuid] = now_mono
        else:
            # No authority field or persisted revision changed, so the
            # in-memory heartbeat can safely advance between disk flushes.
            self._records[credential.document_session_uuid] = updated
        return updated.to_public_dict()


def update_metadata(
    self,
    credential: LeaseCredential,
    *,
    task_summary: str | None = None,
    current_operation: str | None = None,
) -> dict[str, Any]:
    with self._lock:
        record = self._record_for_credential(credential)
        changes: dict[str, Any] = {}
        if task_summary is not None:
            changes["task_summary"] = bounded_diagnostic(
                task_summary,
                1024,
                secrets_to_remove=(credential.token,),
            )
        if current_operation is not None:
            changes["current_operation"] = bounded_diagnostic(
                current_operation,
                512,
                secrets_to_remove=(credential.token,),
            )
        updated = record.revised(**changes)
        return self._commit(record, updated).to_public_dict()
