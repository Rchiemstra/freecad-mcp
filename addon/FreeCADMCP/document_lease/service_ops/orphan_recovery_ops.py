"""Orphan recovery record construction and sidecar commit helpers."""

from __future__ import annotations

import os

from ..errors.coordination_error import CoordinationError
from ..errors.foreign_recovery_error import ForeignRecoveryError
from ..errors.lease_conflict_error import LeaseConflictError
from ..errors.local_recovery_error import LocalRecoveryError
from ..model import (
    LeaseOwner,
    LeaseRecord,
    LeaseState,
    LiveDocumentValidation,
)
from ..sidecar import SidecarCommitUncertainError, SidecarError, sidecar_path_for
from .constants import bounded_text
from .cross_layer_handoff import exact_persisted_record
from .orphan_recovery_validation import (
    assert_replacement_owner_runtime,
    normalize_orphan_snapshot_id,
    rotate_orphan_token_fingerprint,
    validate_orphan_baseline_match,
    validate_orphan_live_validation,
)


def assert_missing_sidecar_recovery_path(identity) -> str:
    path = (
        sidecar_path_for(identity.canonical_path) if identity.canonical_path else None
    )
    if path is None:
        raise ForeignRecoveryError("orphan recovery requires a saved open document")
    if os.path.lexists(path):
        raise CoordinationError("foreign recovery sidecar reappeared before fencing")
    return path


def build_orphan_replacement_record(
    self,
    *,
    identity,
    owner: LeaseOwner,
    previous: LeaseRecord,
    validation: LiveDocumentValidation,
    snapshot_id: str,
    task_summary: str,
    adopt_dirty: bool,
) -> tuple[LeaseRecord, str, int, int]:
    normalized_snapshot = normalize_orphan_snapshot_id(snapshot_id)
    raw_token, replacement_fingerprint = rotate_orphan_token_fingerprint(
        self,
        previous.token_fingerprint,
    )
    generation = (
        max(previous.generation, self._generations.get(identity.session_uuid, 0)) + 1
    )
    now = self._utc_clock()
    now_mono = self._monotonic_ns()
    replacement = LeaseRecord(
        lease_id=str(self._uuid_factory()),
        generation=generation,
        token_fingerprint=replacement_fingerprint,
        document=identity,
        owner=owner,
        state=LeaseState.LOCKED_IDLE,
        record_revision=previous.record_revision + 1,
        state_revision=previous.state_revision + 1,
        acquired_at=now,
        last_heartbeat_at=now,
        monotonic_heartbeat_ns=now_mono,
        heartbeat_sequence=0,
        current_operation="",
        task_summary=bounded_text(task_summary, 1024),
        dirty=bool(adopt_dirty),
        user_intervened=False,
        last_mutation_revision=1 if adopt_dirty else 0,
        last_successful_save_at=None,
        last_verified_save_revision=0,
        baseline=validation.baseline,
        error=None,
        validation_complete=True,
        snapshot_id=normalized_snapshot,
        migration=None,
    )
    return replacement, raw_token, generation, now_mono


def commit_orphan_sidecar_create(self, path: str, replacement: LeaseRecord) -> bool:
    try:
        self.sidecar_store.create(path, replacement)
    except SidecarCommitUncertainError as exc:
        if exc.persisted is not None and not exact_persisted_record(
            self.sidecar_store,
            exc.persisted,
            replacement,
        ):
            raise CoordinationError(
                "orphaned foreign sidecar commit could not be proven",
                details={
                    "commit_uncertain": True,
                    "retain_snapshot": True,
                },
            ) from exc
        return True
    except SidecarError as exc:
        raise CoordinationError(
            f"orphaned foreign authority could not be fenced: {exc}"
        ) from exc
    except Exception as exc:
        raise CoordinationError(
            "orphaned foreign sidecar commit failed with unknown state",
            details={
                "commit_uncertain": True,
                "retain_snapshot": True,
            },
        ) from exc
    return False


def commit_orphan_sidecar_replace(
    self,
    path: str,
    replacement: LeaseRecord,
    current: LeaseRecord,
    *,
    failure_prefix: str,
) -> bool:
    try:
        self.sidecar_store.replace(path, replacement, expected=current)
    except SidecarCommitUncertainError as exc:
        if exc.persisted is not None and not exact_persisted_record(
            self.sidecar_store,
            exc.persisted,
            replacement,
        ):
            raise CoordinationError(
                f"{failure_prefix} sidecar commit could not be proven",
                details={
                    "commit_uncertain": True,
                    "retain_snapshot": True,
                },
            ) from exc
        return True
    except SidecarError as exc:
        raise CoordinationError(
            f"{failure_prefix} authority could not be fenced: {exc}"
        ) from exc
    except Exception as exc:
        raise CoordinationError(
            f"{failure_prefix} sidecar commit failed with unknown state",
            details={
                "commit_uncertain": True,
                "retain_snapshot": True,
            },
        ) from exc
    return False


def prepare_foreign_orphan_recovery(
    self,
    identity,
    foreign,
    owner: LeaseOwner,
    validation: LiveDocumentValidation,
    *,
    adopt_dirty: bool,
    local_confirmation: bool = False,
    snapshot_id: str,
    task_summary: str,
) -> tuple[str, LeaseRecord, LeaseRecord, str, int, int]:
    if foreign.local_document != identity:
        raise ForeignRecoveryError(
            "the live document identity changed after foreign import"
        )
    previous = foreign.persisted
    if not self._is_missing_sidecar_foreign_recovery_candidate(previous):
        raise ForeignRecoveryError(
            "foreign authority lacks a verified recoverable saved baseline"
        )
    if identity.session_uuid in self._pending_save_as:
        raise CoordinationError("orphan recovery is blocked during Save As recovery")
    path = assert_missing_sidecar_recovery_path(identity)
    assert_replacement_owner_runtime(self, owner)
    self._prove_orphaned_foreign_authority_inactive(foreign)
    validate_orphan_live_validation(
        validation,
        identity,
        adopt_dirty=adopt_dirty,
        local_confirmation=local_confirmation,
    )
    validate_orphan_baseline_match(
        self,
        identity,
        validation,
        previous.baseline,
        mismatch_message=(
            "the saved file no longer matches the foreign recovery baseline"
        ),
    )
    replacement, raw_token, generation, now_mono = build_orphan_replacement_record(
        self,
        identity=identity,
        owner=owner,
        previous=previous,
        validation=validation,
        snapshot_id=snapshot_id,
        task_summary=task_summary,
        adopt_dirty=adopt_dirty,
    )
    return path, previous, replacement, raw_token, generation, now_mono


def prepare_local_orphan_recovery(
    self,
    identity,
    owner: LeaseOwner,
    validation: LiveDocumentValidation,
    *,
    snapshot_id: str,
    task_summary: str,
) -> tuple[LeaseRecord, LeaseRecord, str, int, int, str]:
    current = self._records.get(identity.session_uuid)
    if current is None:
        raise LeaseConflictError("the selected document has no local lease to recover")
    if current.document != identity:
        raise CoordinationError(
            "the live document identity changed before orphan recovery"
        )
    if not self._is_recoverable_local_mcp_orphan_candidate(current):
        raise LocalRecoveryError(
            "local lease authority lacks a fully verified saved baseline"
        )
    if current.owner.mcp_instance_id == owner.mcp_instance_id:
        raise LocalRecoveryError(
            "orphan recovery requires a distinct replacement MCP runtime"
        )
    if identity.session_uuid in self._pending_save_as:
        raise CoordinationError("orphan recovery is blocked during Save As recovery")
    self._assert_sidecar_matches(current)
    assert_replacement_owner_runtime(self, owner)
    self._prove_local_mcp_recovery_authority_inactive(current)
    validate_orphan_live_validation(validation, identity, require_clean=True)
    validate_orphan_baseline_match(
        self,
        identity,
        validation,
        current.baseline,
        mismatch_message=(
            "the saved file changed after the orphaned lease was verified"
        ),
    )
    replacement, raw_token, generation, now_mono = build_orphan_replacement_record(
        self,
        identity=identity,
        owner=owner,
        previous=current,
        validation=validation,
        snapshot_id=snapshot_id,
        task_summary=task_summary,
        adopt_dirty=False,
    )
    path = self._sidecar_path(current)
    if path is None:
        raise CoordinationError(
            "local orphan recovery requires a saved document sidecar"
        )
    return current, replacement, raw_token, generation, now_mono, path
