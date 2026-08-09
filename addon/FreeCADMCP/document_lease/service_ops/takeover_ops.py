"""Document lease service operations — takeover ops."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors.lease_conflict_error import LeaseConflictError
from ..errors.lease_state_error import LeaseStateError
from ..errors.local_recovery_error import LocalRecoveryError
from ..model import (
    DocumentSelector,
    LeaseErrorInfo,
    LeaseRecord,
    LeaseState,
    token_fingerprint,
)
from .constants import (
    RECOVERY_IDENTITY_REFRESHABLE_STATES,
    bounded_text,
)


def takeover(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    *,
    dirty: bool | None = None,
    reason: str = "Local user took over the document",
) -> LeaseRecord:
    """Fence the owner locally; the replacement digest has no recoverable token."""

    identity = self.identity_service.resolve(selector)
    with self._lock:
        record = self._records.get(identity.session_uuid)
        if record is None:
            raise LeaseConflictError("the selected document has no active lease")
        self._assert_sidecar_matches(record)
        if record.state == LeaseState.USER_INTERVENED:
            return record
        # ACQUIRING and RELEASING intentionally have no direct user edge;
        # establish uncertainty before applying the takeover fence.
        if record.state in {LeaseState.ACQUIRING, LeaseState.RELEASING}:
            uncertain = record.transitioned(
                LeaseState.LOCKED_ERROR,
                error=LeaseErrorInfo(
                    code="TAKEOVER_DURING_TRANSITION",
                    message=bounded_text(reason, 2048),
                    at=self._utc_clock(),
                ),
            )
            record = self._commit(record, uncertain)
        generation = record.generation + 1
        # Hash a new, immediately discarded secret.  This both rotates away
        # from the old digest and ensures no credential can authorize it.
        revoked_digest = token_fingerprint(self._token_factory())
        updated = record.transitioned(
            LeaseState.USER_INTERVENED,
            generation=generation,
            token_fingerprint=revoked_digest,
            user_intervened=True,
            dirty=record.dirty if dirty is None else bool(dirty),
            error=LeaseErrorInfo(
                code="USER_INTERVENED",
                message=bounded_text(reason, 2048),
                at=self._utc_clock(),
            ),
        )
        self._generations[identity.session_uuid] = generation
        return self._commit(record, updated)


def update_local_dirty(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    *,
    dirty: bool,
) -> LeaseRecord:
    """Refresh authoritative dirty status after a confirmed takeover.

    This token-less method is deliberately limited to already-fenced local
    recovery states.  It cannot revoke an owner, release a sidecar, or make
    a document clean.
    """

    if not isinstance(dirty, bool):
        raise LocalRecoveryError("local dirty status must be true or false")
    identity = self.identity_service.resolve(selector)
    with self._lock:
        record = self._records.get(identity.session_uuid)
        if record is None:
            raise LeaseConflictError("the selected document has no recovery record")
        if record.state not in {
            LeaseState.USER_INTERVENED,
            LeaseState.UNLOCKED_DIRTY,
        }:
            raise LeaseStateError(
                "local dirty status can change only after takeover",
                details={"state": record.state.value},
            )
        self._assert_sidecar_matches(record)
        if record.dirty == dirty:
            return record
        updated = record.revised(
            dirty=dirty,
            validation_complete=(record.validation_complete if not dirty else False),
        )
        return self._commit(record, updated)


def refresh_local_recovery_document_identity(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    *,
    document: Any,
) -> LeaseRecord:
    """Refresh a GUI-saved file identity after takeover or intervention.

    After user intervention the saved file content may differ from the
    lease baseline. This path updates only exact-proxy file-identity
    metadata and deliberately skips baseline revalidation.
    """

    identity = self.identity_service.resolve(selector)
    with self._lock:
        record = self._records.get(identity.session_uuid)
        if record is None:
            raise LeaseConflictError("the selected document has no recovery record")
        if record.state not in RECOVERY_IDENTITY_REFRESHABLE_STATES:
            raise LeaseStateError(
                "saved-file identity can refresh only after takeover",
                details={"state": record.state.value},
            )
        return self._refresh_exact_proxy_file_identity(
            identity.session_uuid,
            document,
            record,
            trigger="local_recovery_refresh",
        )
