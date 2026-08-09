"""Document lease service operations — effective records."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from ..errors.foreign_recovery_record import ForeignRecoveryRecord
from ..model import (
    DocumentSelector,
    LeaseRecord,
    LeaseState,
)
from ..sidecar import (
    SidecarError,
    sidecar_path_for,
)
from .constants import (
    bounded_text,
)


def _coordination_lost_status(
    self, record: LeaseRecord, *, code: str, message: str
) -> dict[str, Any]:
    """Render the conservative effective state without forging authority.

    A missing or conflicting sidecar cannot itself be safely rewritten, so
    status is synthesized from the redacted registry record. Authorization
    still calls ``_assert_sidecar_matches`` and therefore fails closed.
    """

    payload = record.to_public_dict()
    payload["source"] = "local_coordination_error"
    payload["coordination_lost"] = True
    payload["lease"]["state"] = LeaseState.LOCKED_ERROR.value
    payload["lease"]["current_operation"] = "Coordination recovery required"
    payload["document_state"]["error"] = {
        "code": code,
        "message": bounded_text(message, 2048),
        "at": self._effective_error_at(
            record.document.session_uuid, code, record.record_revision
        ),
    }
    return payload


def _effective_error_at(
    self, document_session_uuid: str, code: str, record_revision: int
) -> str:
    """Reuse the first observation time for one synthetic effective error."""

    key = (str(document_session_uuid), str(code), int(record_revision))
    observed_at = self._effective_error_times.get(key)
    if observed_at is None:
        observed_at = self._utc_clock()
        self._effective_error_times[key] = observed_at
    return observed_at


def _clear_effective_error_times(self, document_session_uuid: str) -> None:
    session_uuid = str(document_session_uuid)
    for key in tuple(self._effective_error_times):
        if key[0] == session_uuid:
            self._effective_error_times.pop(key, None)


def _effective_public_record(self, record: LeaseRecord) -> dict[str, Any]:
    path = self._sidecar_path(record)
    if path is None:
        self._clear_effective_error_times(record.document.session_uuid)
        return record.to_public_dict()
    if not os.path.lexists(path):
        return self._coordination_lost_status(
            record,
            code="SIDECAR_MISSING",
            message="The authoritative document sidecar is missing",
        )
    try:
        persisted = self.sidecar_store.read(path)
    except SidecarError as exc:
        return self._coordination_lost_status(
            record,
            code="SIDECAR_INVALID",
            message=f"The authoritative document sidecar is invalid: {exc}",
        )
    if not self._authority_equal(record, persisted):
        return self._coordination_lost_status(
            record,
            code="SIDECAR_AUTHORITY_MISMATCH",
            message="Registry and sidecar lease authority do not match",
        )
    self._clear_effective_error_times(record.document.session_uuid)
    return record.to_public_dict()


def _effective_foreign_public(self, foreign: ForeignRecoveryRecord) -> dict[str, Any]:
    payload = foreign.to_public_dict()
    session_uuid = foreign.local_document.session_uuid
    record_revision = foreign.persisted.record_revision
    canonical_path = foreign.local_document.canonical_path
    if not canonical_path:
        payload["coordination_lost"] = True
        payload["lease"]["state"] = LeaseState.LOCKED_ERROR.value
        payload["document_state"]["error"] = {
            "code": "FOREIGN_DOCUMENT_IDENTITY_INVALID",
            "message": "Foreign recovery is not bound to a saved document",
            "at": self._effective_error_at(
                session_uuid,
                "FOREIGN_DOCUMENT_IDENTITY_INVALID",
                record_revision,
            ),
        }
        return payload
    path = sidecar_path_for(canonical_path)
    try:
        persisted = self.sidecar_store.read(path)
    except SidecarError as exc:
        payload["coordination_lost"] = True
        payload["lease"]["state"] = LeaseState.LOCKED_ERROR.value
        payload["document_state"]["error"] = {
            "code": "FOREIGN_SIDECAR_INVALID",
            "message": bounded_text(str(exc), 2048),
            "at": self._effective_error_at(
                session_uuid, "FOREIGN_SIDECAR_INVALID", record_revision
            ),
        }
        return payload
    if persisted != foreign.persisted:
        payload["coordination_lost"] = True
        payload["lease"]["state"] = LeaseState.LOCKED_ERROR.value
        payload["document_state"]["error"] = {
            "code": "FOREIGN_AUTHORITY_CHANGED",
            "message": "Foreign recovery authority changed after import",
            "at": self._effective_error_at(
                session_uuid, "FOREIGN_AUTHORITY_CHANGED", record_revision
            ),
        }
    else:
        self._clear_effective_error_times(session_uuid)
    return payload


def get_effective(
    self, selector: DocumentSelector | Mapping[str, Any] | str
) -> dict[str, Any] | None:
    """Return the most restrictive registry/sidecar status."""

    identity = self.identity_service.resolve(selector)
    with self._lock:
        record = self._records.get(identity.session_uuid)
        if record is not None:
            return self._effective_public_record(record)
        foreign = self._foreign_records.get(identity.session_uuid)
        return self._effective_foreign_public(foreign) if foreign is not None else None


def list_effective_records(self) -> list[dict[str, Any]]:
    """Return redacted effective status for GUI and public RPC reads."""

    with self._lock:
        local = [
            self._effective_public_record(record) for record in self._records.values()
        ]
        foreign = [
            self._effective_foreign_public(record)
            for record in self._foreign_records.values()
        ]
        return local + foreign
