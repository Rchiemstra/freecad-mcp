"""Public identity-refresh entry points for leased documents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors.lease_conflict_error import LeaseConflictError
from ..errors.lease_service_error import LeaseServiceError
from ..model import DocumentIdentity, DocumentSelector, LeaseRecord


def try_baseline_preserving_document_identity_refresh(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    *,
    document: Any,
    trigger: str = "gui_save_finish",
) -> LeaseRecord | None:
    """Repair a leased document in place when only file identity changed."""

    identity = self.identity_service.resolve(selector)
    with self._lock:
        record = self._records.get(identity.session_uuid)
        if record is None:
            return None
        try:
            return self._apply_baseline_preserving_identity_refresh(
                identity.session_uuid,
                document,
                record,
                trigger=trigger,
            )
        except LeaseServiceError:
            return None


def repair_registered_document_identity(self, *, document: Any) -> DocumentIdentity:
    """Repair exact-proxy identity drift for a registered leased document."""

    session_uuid = self.identity_service.registered_session_uuid(document)
    with self._lock:
        record = self._records.get(session_uuid)
        if record is None:
            raise LeaseConflictError(
                "the registered document has no local lease record"
            )
        self._apply_baseline_preserving_identity_refresh(
            session_uuid,
            document,
            record,
            trigger="registration_recovery",
        )
        return self.identity_service.inspect_registered_document(session_uuid, document)
