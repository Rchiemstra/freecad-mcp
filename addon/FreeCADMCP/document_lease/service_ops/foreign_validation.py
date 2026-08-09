"""Document lease service operations — foreign validation."""

from __future__ import annotations

import os

from ..errors.foreign_recovery_error import ForeignRecoveryError
from ..identity import (
    DocumentIdentityError,
    canonicalize_path,
    file_identity_for_path,
)
from ..model import (
    DocumentIdentity,
    LeaseRecord,
    LeaseState,
    SaveAsMigrationRole,
)


def _assert_foreign_document_exact(
    self,
    local: DocumentIdentity,
    persisted: LeaseRecord,
    *,
    allow_unreturned_file_replacement: bool = False,
    allow_saved_dirty_file_replacement: bool = False,
) -> None:
    """Require the adjacent record to describe the exact currently-open file."""

    if not local.canonical_path or not local.comparison_key:
        raise ForeignRecoveryError(
            "foreign sidecar import requires a saved open document"
        )
    if not os.path.isfile(local.canonical_path):
        raise ForeignRecoveryError(
            "the open document path is missing or is not a regular file"
        )
    foreign_document = persisted.document
    if not foreign_document.canonical_path or not foreign_document.comparison_key:
        raise ForeignRecoveryError(
            "the foreign record does not identify a saved document"
        )
    try:
        _canonical, foreign_comparison = canonicalize_path(
            foreign_document.canonical_path,
            platform=self.identity_service.platform,
        )
    except Exception as exc:
        raise ForeignRecoveryError(
            f"the foreign document path is invalid: {exc}"
        ) from exc
    if (
        foreign_comparison != foreign_document.comparison_key
        or foreign_comparison != local.comparison_key
    ):
        raise ForeignRecoveryError(
            "the adjacent sidecar identifies a different document path"
        )
    try:
        observed_identity = file_identity_for_path(
            local.canonical_path, platform=self.identity_service.platform
        )
    except (OSError, DocumentIdentityError) as exc:
        raise ForeignRecoveryError(
            f"the open document file identity cannot be verified: {exc}"
        ) from exc
    if local.file_identity != observed_identity:
        raise ForeignRecoveryError(
            "the registered open-document file identity is no longer current"
        )
    unverified_destination = (
        persisted.state == LeaseState.ACQUIRING
        and persisted.migration is not None
        and persisted.migration.role == SaveAsMigrationRole.DESTINATION
        and persisted.baseline is None
        and not persisted.validation_complete
    )
    saved_dirty_recovery = bool(
        allow_saved_dirty_file_replacement
        and self._is_saved_dirty_foreign_candidate(persisted)
    )
    if (
        foreign_document.file_identity != observed_identity
        and not unverified_destination
        and not saved_dirty_recovery
        and not (
            allow_unreturned_file_replacement
            and self._is_unreturned_reservation(
                persisted,
                allow_active_acquiring=True,
            )
        )
    ):
        raise ForeignRecoveryError(
            "the adjacent sidecar identifies a different filesystem file"
        )
    if (
        persisted.baseline is not None
        and persisted.baseline.file_identity != foreign_document.file_identity
        and not saved_dirty_recovery
    ):
        raise ForeignRecoveryError(
            "the foreign baseline and document file identities disagree"
        )


def _is_clean_orphaned_foreign_candidate(record: LeaseRecord) -> bool:
    """Recognize authority that proves all mutations reached a clean save."""

    return bool(
        record.state == LeaseState.LOCKED_IDLE
        and not record.dirty
        and not record.user_intervened
        and record.error is None
        and record.baseline is not None
        and record.validation_complete
        and record.last_verified_save_revision == record.last_mutation_revision
        and record.migration is None
    )


def _is_missing_sidecar_foreign_recovery_candidate(
    cls,
    record: LeaseRecord,
) -> bool:
    """Recognize the only cached foreign records safe to re-fence.

    The normal case is a fully validated clean lease.  The legacy exception
    is deliberately narrower: older builds could mistake their own worker
    ``saveCopy`` snapshot for a user save and rotate an otherwise verified
    lease to ``USER_INTERVENED``.  That transition clears neither the saved
    baseline nor the equality proving every recorded mutation had already
    reached disk.  The live document's current ``Modified`` flag still
    controls whether recovery must use dirty adoption; this predicate never
    treats unsaved state as clean.
    """

    legacy_worker_snapshot = bool(
        cls._is_misattributed_worker_snapshot_intervention(record)
        and record.document.canonical_path is not None
        and record.baseline is not None
        and record.last_verified_save_revision == record.last_mutation_revision
        and record.migration is None
    )
    return bool(
        cls._is_clean_orphaned_foreign_candidate(record) or legacy_worker_snapshot
    )


def _is_recoverable_local_mcp_orphan_candidate(record: LeaseRecord) -> bool:
    """Recognize local authority that fresh clean evidence can safely fence.

    ``USER_INTERVENED`` is accepted only when the prior lease had already
    verified every mutation at its saved baseline. A narrowly recognized
    legacy worker ``saveCopy`` false-positive can rely on the credential
    already irrevocably rotated by takeover even without an MCP hostname;
    other intervention records still require dead-owner proof. The later
    handoff always requires a clean live document and an independently
    re-hashed, byte-identical saved file.
    """

    clean_idle = bool(
        record.state == LeaseState.LOCKED_IDLE
        and not record.dirty
        and not record.user_intervened
        and record.error is None
        and record.validation_complete
    )
    clean_stale = bool(
        record.state == LeaseState.STALE
        and not record.dirty
        and not record.user_intervened
        and record.error is not None
        and record.error.code in {"LEASE_STALE", "LEASE_OWNER_EXITED"}
        and record.validation_complete
    )
    verified_intervention = bool(
        record.state == LeaseState.USER_INTERVENED
        and record.user_intervened
        and record.error is not None
        and record.error.code == "USER_INTERVENED"
    )
    return bool(
        (clean_idle or clean_stale or verified_intervention)
        and record.document.canonical_path is not None
        and record.baseline is not None
        and record.last_verified_save_revision == record.last_mutation_revision
        and record.migration is None
    )


def _is_saved_dirty_foreign_candidate(record: LeaseRecord) -> bool:
    """Recognize explicit local dirty recovery that a later save can resolve.

    ``UNLOCKED_DIRTY`` has no usable agent credential: local takeover already
    rotated the generation, and the subsequent acknowledgement deliberately
    retained only recovery authority. A new runtime may therefore supersede
    it after proving the old FreeCAD owner dead, independently validating
    the current saved file, and either observing a clean live document or
    completing the normal confirmed dirty-adoption flow.
    """

    return bool(
        record.state == LeaseState.UNLOCKED_DIRTY
        and record.dirty
        and record.user_intervened
        and record.error is not None
        and record.error.code == "DIRTY_ACKNOWLEDGED"
        and record.baseline is not None
        and record.migration is None
    )


def _is_abandoned_locked_error_foreign_candidate(record: LeaseRecord) -> bool:
    """Recognize errored dirty authority stranded by a dead FreeCAD runtime.

    The recovery snapshot and original saved-file baseline make this
    distinguishable from an arbitrary active/error sidecar. Acquisition
    still has to prove the recorded FreeCAD owner dead and prove that the
    currently saved file is the exact original baseline before authority
    can be rotated.
    """

    return bool(
        record.state == LeaseState.LOCKED_ERROR
        and record.dirty
        and not record.user_intervened
        and record.error is not None
        and record.baseline is not None
        and record.snapshot_id is not None
        and record.migration is None
    )
