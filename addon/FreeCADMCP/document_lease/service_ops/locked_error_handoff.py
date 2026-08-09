"""Document lease service operations — locked error handoff."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Any

from ..errors.coordination_error import CoordinationError
from ..errors.dirty_adoption_error import DirtyAdoptionError
from ..errors.lease_conflict_error import LeaseConflictError
from ..errors.lease_grant import LeaseGrant
from ..errors.lease_service_error import LeaseServiceError
from ..errors.lease_state_error import LeaseStateError
from ..errors.live_document_validation_error import LiveDocumentValidationError
from ..model import (
    DocumentSelector,
    FileBaseline,
    LeaseCredential,
    LeaseOwner,
    LeaseState,
    LiveDocumentValidation,
    token_fingerprint,
)
from ..sidecar import (
    SidecarError,
)
from .constants import (
    bounded_text,
)


def _assert_locked_error_recovery_evidence(current) -> None:
    if (
        not current.dirty
        or current.user_intervened
        or current.error is None
        or current.baseline is None
        or current.snapshot_id is None
        or current.migration is not None
    ):
        raise DirtyAdoptionError(
            "LOCKED_ERROR authority lacks complete dirty recovery evidence"
        )


def _assert_locked_error_runtime_match(self, current, owner: LeaseOwner) -> None:
    local = self._local_runtime_identity
    if local is None:
        raise CoordinationError("local runtime identity is unavailable")
    expected_runtime = (
        local.addon_profile_id,
        local.addon_runtime_id,
        local.freecad_pid,
        local.freecad_process_started_at,
        local.boot_id,
    )
    if (
        current.owner.addon_profile_id,
        current.owner.addon_runtime_id,
        current.owner.freecad_pid,
        current.owner.freecad_process_started_at,
        current.owner.boot_id,
    ) != expected_runtime:
        raise CoordinationError(
            "LOCKED_ERROR authority does not belong to this FreeCAD runtime"
        )
    if (
        owner.addon_profile_id,
        owner.addon_runtime_id,
        owner.freecad_pid,
        owner.freecad_process_started_at,
        owner.boot_id,
    ) != expected_runtime:
        raise CoordinationError(
            "replacement owner does not belong to this FreeCAD runtime"
        )


def _validate_locked_error_handoff_evidence(
    self,
    identity,
    current,
    validation: LiveDocumentValidation,
) -> None:
    if not isinstance(validation, LiveDocumentValidation):
        raise LiveDocumentValidationError(
            "fresh LiveDocumentValidation evidence is required"
        )
    if validation.document != identity:
        raise LiveDocumentValidationError(
            "live document evidence does not match the registered document"
        )
    if validation.document_modified is not True:
        raise DirtyAdoptionError(
            "LOCKED_ERROR handoff requires a currently dirty live document"
        )
    if validation.baseline_validated is not True or not isinstance(
        validation.baseline, FileBaseline
    ):
        raise LiveDocumentValidationError(
            "LOCKED_ERROR handoff requires a validated saved-file baseline"
        )
    if validation.baseline != current.baseline:
        raise LiveDocumentValidationError(
            "the saved file changed after the errored lease was acquired"
        )
    self._assert_current_baseline(
        identity,
        validation.baseline,
        error_type=LiveDocumentValidationError,
    )


def claim_locked_error_handoff(
    self,
    selector: DocumentSelector | Mapping[str, Any] | str,
    owner: LeaseOwner,
    *,
    validation: LiveDocumentValidation,
    local_confirmation: bool,
    task_summary: str = "",
) -> LeaseGrant:
    """Fence an errored local credential into a confirmed new MCP owner.

    ``LOCKED_ERROR`` proves the previous operation has finished and the
    document remains fenced. Explicit local GUI confirmation authorizes a
    new MCP client to continue the dirty document without closing it. The
    original acquisition baseline and recovery snapshot are preserved while
    lease ID, generation, token digest, and owner are atomically rotated.
    """

    if local_confirmation is not True:
        raise DirtyAdoptionError(
            "LOCKED_ERROR handoff requires explicit local GUI confirmation"
        )
    identity = self.identity_service.resolve(selector)
    with self._lock:
        current = self._records.get(identity.session_uuid)
        if current is None:
            raise LeaseConflictError(
                "the selected document has no local lease to hand off"
            )
        if current.state != LeaseState.LOCKED_ERROR:
            raise LeaseStateError(
                "credential handoff requires a LOCKED_ERROR lease",
                details={"state": current.state.value},
            )
        if identity.session_uuid in self._pending_save_as:
            raise CoordinationError(
                "credential handoff is blocked during Save As recovery"
            )
        self._assert_sidecar_matches(current)
        _assert_locked_error_recovery_evidence(current)
        _assert_locked_error_runtime_match(self, current, owner)
        _validate_locked_error_handoff_evidence(self, identity, current, validation)

        raw_token = self._token_factory()
        if not raw_token:
            raise LeaseServiceError("token factory returned an empty token")
        replacement_fingerprint = token_fingerprint(raw_token)
        if secrets.compare_digest(
            replacement_fingerprint,
            current.token_fingerprint,
        ):
            raise LeaseServiceError("token factory did not rotate the fencing digest")
        generation = (
            max(
                current.generation,
                self._generations.get(identity.session_uuid, 0),
            )
            + 1
        )
        now = self._utc_clock()
        now_mono = self._monotonic_ns()
        # This is an authority handoff, not a document-state mutation.
        # Publish the final idle successor as one CAS revision so the
        # sidecar store never exposes an intermediate owner/state pair.
        claimed = current.revised(
            state=LeaseState.LOCKED_IDLE,
            state_revision=current.state_revision + 1,
            lease_id=str(self._uuid_factory()),
            generation=generation,
            token_fingerprint=replacement_fingerprint,
            owner=owner,
            acquired_at=now,
            last_heartbeat_at=now,
            monotonic_heartbeat_ns=now_mono,
            heartbeat_sequence=0,
            current_operation="",
            task_summary=bounded_text(task_summary, 1024),
            dirty=True,
            error=None,
            validation_complete=False,
        )
        path = self._sidecar_path(current)
        if path is None:
            raise CoordinationError(
                "LOCKED_ERROR handoff requires a saved document sidecar"
            )
        try:
            self.sidecar_store.replace(path, claimed, expected=current)
        except SidecarError as exc:
            raise CoordinationError(
                f"LOCKED_ERROR credential handoff could not be fenced: {exc}"
            ) from exc
        self._records[identity.session_uuid] = claimed
        self._generations[identity.session_uuid] = generation
        self._last_sidecar_heartbeat_ns[identity.session_uuid] = now_mono
        self._clear_effective_error_times(identity.session_uuid)
        credential = LeaseCredential(
            lease_id=claimed.lease_id,
            document_session_uuid=identity.session_uuid,
            generation=generation,
            token=raw_token,
            mcp_instance_id=owner.mcp_instance_id,
        )
        return LeaseGrant(credential=credential, record=claimed)
