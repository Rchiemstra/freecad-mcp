"""Document lease service operations — saved foreign acquisition."""

from __future__ import annotations

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


def _read_saved_foreign_recovery_persisted(self, identity, previous):
    path = (
        sidecar_path_for(identity.canonical_path) if identity.canonical_path else None
    )
    if path is None:
        raise ForeignRecoveryError(
            "saved foreign recovery requires a saved open document"
        )
    try:
        persisted = self.sidecar_store.read(path)
    except SidecarError as exc:
        raise CoordinationError(
            f"saved foreign recovery sidecar is unavailable or invalid: {exc}"
        ) from exc
    if persisted != previous:
        raise CoordinationError(
            "saved foreign recovery authority changed before fencing"
        )
    self._assert_foreign_document_exact(
        identity,
        persisted,
        allow_saved_dirty_file_replacement=True,
    )
    return path


def _validate_saved_foreign_recovery_evidence(
    self,
    identity,
    previous,
    validation: LiveDocumentValidation,
    *,
    adopt_dirty: bool,
    local_confirmation: bool,
    abandoned_locked_error: bool,
) -> None:
    validate_orphan_live_validation(
        validation,
        identity,
        adopt_dirty=adopt_dirty,
        local_confirmation=local_confirmation,
    )
    if abandoned_locked_error and validation.baseline != previous.baseline:
        raise LiveDocumentValidationError(
            "the saved file no longer matches the errored lease baseline"
        )
    self._assert_current_baseline(
        identity,
        validation.baseline,
        error_type=LiveDocumentValidationError,
    )


def begin_saved_foreign_recovery_acquisition(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    owner: LeaseOwner,
    *,
    validation: LiveDocumentValidation,
    task_summary: str = "",
    adopt_dirty: bool = False,
    local_confirmation: bool = False,
) -> LeaseGrant:
    """CAS-fence recoverable dirty authority for a verified live document.

    This path never deletes coordination data and never trusts the stale
    record's old baseline as current file evidence. It requires an exact
    same-path imported record, proof that its FreeCAD owner is dead, and
    a freshly captured baseline for the currently saved file.
    ``UNLOCKED_DIRTY`` may follow a later user save, while ``LOCKED_ERROR``
    must still match its original saved-file baseline exactly. A dirty
    live document additionally requires the normal explicit local GUI
    adoption confirmation. The existing sidecar is then atomically
    replaced by new ``ACQUIRING`` authority, so no unlocked filesystem gap
    is introduced.
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
        acknowledged_dirty = self._is_saved_dirty_foreign_candidate(previous)
        abandoned_locked_error = self._is_abandoned_locked_error_foreign_candidate(
            previous
        )
        if not acknowledged_dirty and not abandoned_locked_error:
            raise ForeignRecoveryError(
                "foreign authority is not recoverable dirty authority"
            )
        path = _read_saved_foreign_recovery_persisted(self, identity, previous)
        self._prove_foreign_owner_dead(previous.owner)
        _validate_saved_foreign_recovery_evidence(
            self,
            identity,
            previous,
            validation,
            adopt_dirty=adopt_dirty,
            local_confirmation=local_confirmation,
            abandoned_locked_error=abandoned_locked_error,
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
            dirty=bool(adopt_dirty),
            last_mutation_revision=1 if adopt_dirty else 0,
            baseline=None,
            validation_complete=False,
            snapshot_id=None,
        )
        try:
            self.sidecar_store.replace(path, replacement, expected=previous)
        except SidecarError as exc:
            raise CoordinationError(
                f"saved foreign recovery could not be fenced: {exc}"
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
