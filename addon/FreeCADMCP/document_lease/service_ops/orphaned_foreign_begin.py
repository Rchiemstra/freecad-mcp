"""Document lease service operations — orphaned foreign begin."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from ..errors.coordination_error import CoordinationError
from ..errors.foreign_recovery_error import ForeignRecoveryError
from ..errors.lease_conflict_error import LeaseConflictError
from ..errors.lease_grant import LeaseGrant
from ..errors.lease_service_error import LeaseServiceError
from ..errors.live_document_validation_error import LiveDocumentValidationError
from ..model import (
    DocumentSelector,
    LeaseCredential,
    LeaseOwner,
    LeaseRecord,
    LeaseState,
    LiveDocumentValidation,
    token_fingerprint,
)
from ..sidecar import (
    SidecarError,
    sidecar_path_for,
)
from .constants import (
    bounded_text,
)
from .orphan_recovery_validation import validate_orphan_live_validation


def begin_orphaned_foreign_acquisition(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    owner: LeaseOwner,
    *,
    validation: LiveDocumentValidation,
    task_summary: str = "",
) -> LeaseGrant:
    """Atomically fence a clean foreign record whose sidecar disappeared.

    This is the sole automatic missing-sidecar recovery path. It requires
    fresh clean-document evidence and a full saved-file baseline matching
    the last validated clean authority. Publication uses atomic create, so
    a sidecar that reappears or is concurrently recreated wins the race and
    recovery fails closed.
    """

    identity = self.identity_service.resolve(selector)
    with self._lock:
        foreign = self._foreign_records.get(identity.session_uuid)
        if foreign is None:
            raise LeaseConflictError(
                "the selected document has no foreign recovery record"
            )
        if foreign.local_document != identity:
            raise ForeignRecoveryError(
                "the live document identity changed after foreign import"
            )
        previous = foreign.persisted
        if not self._is_clean_orphaned_foreign_candidate(previous):
            raise ForeignRecoveryError(
                "foreign authority does not prove a fully saved clean document"
            )
        path = (
            sidecar_path_for(identity.canonical_path)
            if identity.canonical_path
            else None
        )
        if path is None:
            raise ForeignRecoveryError("orphan recovery requires a saved open document")
        if os.path.lexists(path):
            raise CoordinationError(
                "foreign recovery sidecar reappeared before fencing"
            )
        self._prove_orphaned_foreign_authority_inactive(foreign)
        validate_orphan_live_validation(validation, identity)
        if validation.baseline != previous.baseline:
            raise LiveDocumentValidationError(
                "the saved file no longer matches the foreign clean baseline"
            )
        self._assert_current_baseline(
            identity,
            validation.baseline,
            error_type=LiveDocumentValidationError,
        )

        raw_token = self._token_factory()
        if not raw_token:
            raise LeaseServiceError("token factory returned an empty token")
        generation = (
            max(
                previous.generation,
                self._generations.get(identity.session_uuid, 0),
            )
            + 1
        )
        now = self._utc_clock()
        now_mono = self._monotonic_ns()
        replacement = LeaseRecord(
            lease_id=str(self._uuid_factory()),
            generation=generation,
            token_fingerprint=token_fingerprint(raw_token),
            document=identity,
            owner=owner,
            state=LeaseState.ACQUIRING,
            record_revision=previous.record_revision + 1,
            state_revision=previous.state_revision + 1,
            acquired_at=now,
            last_heartbeat_at=now,
            monotonic_heartbeat_ns=now_mono,
            task_summary=bounded_text(task_summary, 1024),
            dirty=False,
            last_mutation_revision=0,
            baseline=None,
            validation_complete=False,
            snapshot_id=None,
        )
        try:
            self.sidecar_store.create(path, replacement)
        except SidecarError as exc:
            raise CoordinationError(
                f"orphaned foreign authority could not be fenced: {exc}"
            ) from exc
        self._records[identity.session_uuid] = replacement
        self._foreign_records.pop(identity.session_uuid, None)
        self._closed_documents.pop(identity.session_uuid, None)
        self._generations[identity.session_uuid] = generation
        self._last_sidecar_heartbeat_ns[identity.session_uuid] = now_mono
        self._clear_effective_error_times(identity.session_uuid)
        credential = LeaseCredential(
            lease_id=replacement.lease_id,
            document_session_uuid=identity.session_uuid,
            generation=generation,
            token=raw_token,
            mcp_instance_id=owner.mcp_instance_id,
        )
        return LeaseGrant(credential=credential, record=replacement)
