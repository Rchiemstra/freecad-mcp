"""Authoritative in-process registry for version-2 document leases."""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

# §3.3 compatibility shims — moved types keep their legacy import path.
from .errors.authorization_error import AuthorizationError  # noqa: F401
from .errors.cancellation_context import _CancellationContext
from .errors.clean_release_error import CleanReleaseError  # noqa: F401
from .errors.coordination_error import CoordinationError  # noqa: F401
from .errors.dirty_acquisition_error import DirtyAcquisitionError  # noqa: F401
from .errors.dirty_adoption_error import DirtyAdoptionError  # noqa: F401
from .errors.document_identity_refresh_event import DocumentIdentityRefreshEvent
from .errors.foreign_recovery_error import ForeignRecoveryError  # noqa: F401
from .errors.foreign_recovery_record import ForeignRecoveryRecord
from .errors.lease_conflict_error import LeaseConflictError  # noqa: F401
from .errors.lease_grant import LeaseGrant  # noqa: F401
from .errors.lease_service_error import LeaseServiceError  # noqa: F401
from .errors.lease_state_error import LeaseStateError  # noqa: F401
from .errors.live_document_validation_error import LiveDocumentValidationError  # noqa: F401
from .errors.local_recovery_error import LocalRecoveryError  # noqa: F401
from .errors.local_runtime_identity import LocalRuntimeIdentity
from .errors.locked_error_handoff_required import LockedErrorHandoffRequired  # noqa: F401
from .errors.orphaned_foreign_recovery_required import OrphanedForeignRecoveryRequired  # noqa: F401
from .errors.orphaned_local_mcp_recovery_required import (  # noqa: F401
    OrphanedLocalMcpRecoveryRequired,
)
from .errors.process_liveness_evidence import ProcessLivenessEvidence
from .errors.saved_foreign_recovery_required import SavedForeignRecoveryRequired  # noqa: F401
from .identity import (
    DocumentIdentityError,  # noqa: F401
    DocumentIdentityService,
    canonicalize_path,  # noqa: F401
    capture_file_baseline,  # noqa: F401
    file_identity_for_path,  # noqa: F401
)
from .model import (
    DocumentIdentity,
    DocumentSelector,  # noqa: F401
    FileBaseline,  # noqa: F401
    FileIdentity,  # noqa: F401
    LeaseCredential,  # noqa: F401
    LeaseErrorInfo,  # noqa: F401
    LeaseOwner,  # noqa: F401
    LeaseRecord,
    LeaseState,  # noqa: F401
    LiveDocumentValidation,  # noqa: F401
    SaveAsMigration,  # noqa: F401
    SaveAsMigrationRole,  # noqa: F401
    token_fingerprint,  # noqa: F401
    token_matches,  # noqa: F401
    utc_now,
)
from .service_ops import facade_bindings as _ops
from .service_ops.constants import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,  # noqa: F401
    DEFAULT_SIDECAR_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_STALE_AFTER_SECONDS,
    MCP_PROCESS_START_FUTURE_TOLERANCE_SECONDS,  # noqa: F401
)
from .sidecar import (
    SidecarCommitUncertainError,  # noqa: F401
    SidecarError,  # noqa: F401
    SidecarStore,
    sidecar_path_for,  # noqa: F401
)


class DocumentLeaseService:
    """Own state transitions, credential fencing, and sidecar synchronization.

    Registry records never contain raw tokens.  All mutating APIs take a full
    :class:`LeaseCredential`; there is no same-instance or token-less shortcut.
    """

    def __init__(
        self,
        identity_service: DocumentIdentityService,
        sidecar_store: SidecarStore | None = None,
        *,
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
        uuid_factory: Callable[[], uuid.UUID | str] = uuid.uuid4,
        utc_clock: Callable[[], str] = utc_now,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
        sidecar_heartbeat_interval_seconds: float = (
            DEFAULT_SIDECAR_HEARTBEAT_INTERVAL_SECONDS
        ),
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        local_runtime_identity: LocalRuntimeIdentity | None = None,
        process_liveness_probe: (
            Callable[[int], ProcessLivenessEvidence] | None
        ) = None,
    ) -> None:
        self.identity_service = identity_service
        self.sidecar_store = sidecar_store or SidecarStore()
        self._token_factory = token_factory
        self._uuid_factory = uuid_factory
        self._utc_clock = utc_clock
        self._monotonic_ns = monotonic_ns
        self._sidecar_heartbeat_ns = int(sidecar_heartbeat_interval_seconds * 1e9)
        self._stale_after_ns = int(stale_after_seconds * 1e9)
        self._records: dict[str, LeaseRecord] = {}
        self._generations: dict[str, int] = {}
        self._last_sidecar_heartbeat_ns: dict[str, int] = {}
        self._pending_save_as: dict[str, LeaseRecord] = {}
        self._cancellations: dict[str, _CancellationContext] = {}
        self._foreign_records: dict[str, ForeignRecoveryRecord] = {}
        self._closed_documents: dict[str, tuple[int, DocumentIdentity]] = {}
        self._effective_error_times: dict[tuple[str, str, int], str] = {}
        self._acquiring_request_ids: dict[str, str] = {}
        self._local_runtime_identity = local_runtime_identity
        self._process_liveness_probe = process_liveness_probe
        self._identity_refresh_events: list[DocumentIdentityRefreshEvent] = []
        self._lock = threading.RLock()

    def list_identity_refresh_events(self) -> list[dict[str, Any]]:
        """Return token-free records of every automatic identity refresh."""
        with self._lock:
            return [event.to_dict() for event in self._identity_refresh_events]

    @property
    def local_runtime_identity(self) -> LocalRuntimeIdentity | None:
        """Return immutable addon-owned recovery evidence."""
        return self._local_runtime_identity

    _sidecar_path = staticmethod(_ops._sidecar_path)
    _authority_equal = staticmethod(_ops._authority_equal)
    _is_clean_orphaned_foreign_candidate = staticmethod(
        _ops._is_clean_orphaned_foreign_candidate
    )
    _is_missing_sidecar_foreign_recovery_candidate = classmethod(
        _ops._is_missing_sidecar_foreign_recovery_candidate
    )
    _is_recoverable_local_mcp_orphan_candidate = staticmethod(
        _ops._is_recoverable_local_mcp_orphan_candidate
    )
    _is_saved_dirty_foreign_candidate = staticmethod(
        _ops._is_saved_dirty_foreign_candidate
    )
    _is_abandoned_locked_error_foreign_candidate = staticmethod(
        _ops._is_abandoned_locked_error_foreign_candidate
    )
    _parse_timestamp = staticmethod(_ops._parse_timestamp)
    _is_misattributed_worker_snapshot_intervention = staticmethod(
        _ops._is_misattributed_worker_snapshot_intervention
    )
    _is_unreturned_reservation = staticmethod(_ops._is_unreturned_reservation)
    _assert_sidecar_matches = _ops._assert_sidecar_matches
    _assert_foreign_document_exact = _ops._assert_foreign_document_exact
    _prove_foreign_owner_dead = _ops._prove_foreign_owner_dead
    _prove_local_mcp_owner_dead = _ops._prove_local_mcp_owner_dead
    _prove_local_mcp_recovery_authority_inactive = (
        _ops._prove_local_mcp_recovery_authority_inactive
    )
    _prove_orphaned_foreign_authority_inactive = (
        _ops._prove_orphaned_foreign_authority_inactive
    )
    _assert_current_baseline = _ops._assert_current_baseline
    _assert_on_disk_matches_accepted_baseline = (
        _ops._assert_on_disk_matches_accepted_baseline
    )
    _record_identity_refresh_event = _ops._record_identity_refresh_event
    _refresh_exact_proxy_file_identity = _ops._refresh_exact_proxy_file_identity
    _apply_baseline_preserving_identity_refresh = (
        _ops._apply_baseline_preserving_identity_refresh
    )
    try_baseline_preserving_document_identity_refresh = (
        _ops.try_baseline_preserving_document_identity_refresh
    )
    repair_registered_document_identity = _ops.repair_registered_document_identity
    _validate_live_evidence = _ops._validate_live_evidence
    _commit = _ops._commit
    _record_for_credential = _ops._record_for_credential
    acquire = _ops.acquire
    begin_acquisition = _ops.begin_acquisition
    begin_dirty_adoption = _ops.begin_dirty_adoption
    _begin_acquisition_record = _ops._begin_acquisition_record
    recover_orphaned_local_mcp_acquisition = _ops.recover_orphaned_local_mcp_acquisition
    begin_orphaned_foreign_acquisition = _ops.begin_orphaned_foreign_acquisition
    recover_orphaned_foreign_acquisition = _ops.recover_orphaned_foreign_acquisition
    begin_saved_foreign_recovery_acquisition = (
        _ops.begin_saved_foreign_recovery_acquisition
    )
    claim_locked_error_handoff = _ops.claim_locked_error_handoff
    _remember_acquiring_request = _ops._remember_acquiring_request
    _clear_acquiring_request = _ops._clear_acquiring_request
    _may_fence_local_active_acquiring = _ops._may_fence_local_active_acquiring
    _replace_unreturned_reservation = _ops._replace_unreturned_reservation
    complete_dirty_adoption = _ops.complete_dirty_adoption
    record_acquisition_snapshot = _ops.record_acquisition_snapshot
    complete_acquisition = _ops.complete_acquisition
    _complete_acquisition_record = _ops._complete_acquisition_record
    abort_acquisition = _ops.abort_acquisition
    fail_acquisition_after_mutation = _ops.fail_acquisition_after_mutation
    authorize = _ops.authorize
    heartbeat = _ops.heartbeat
    update_metadata = _ops.update_metadata
    begin_mutation = _ops.begin_mutation
    begin_recovery = _ops.begin_recovery
    begin_recompute = _ops.begin_recompute
    complete_operation = _ops.complete_operation
    record_error = _ops.record_error
    begin_save = _ops.begin_save
    cancel_save_before_mutation = _ops.cancel_save_before_mutation
    begin_cancellation = _ops.begin_cancellation
    complete_cancellation = _ops.complete_cancellation
    reserve_save_as = _ops.reserve_save_as
    commit_save_as = _ops.commit_save_as
    mark_save_verified = _ops.mark_save_verified
    import_adjacent_foreign_recovery = _ops.import_adjacent_foreign_recovery
    confirmed_takeover_foreign_recovery = _ops.confirmed_takeover_foreign_recovery
    takeover = _ops.takeover
    update_local_dirty = _ops.update_local_dirty
    refresh_local_recovery_document_identity = (
        _ops.refresh_local_recovery_document_identity
    )
    handle_document_closed = _ops.handle_document_closed
    rebind_closed_recovery_document = _ops.rebind_closed_recovery_document
    acknowledge_local_dirty = _ops.acknowledge_local_dirty
    complete_local_save_and_clear = _ops.complete_local_save_and_clear
    mark_stale = _ops.mark_stale
    mark_expired_stale = _ops.mark_expired_stale
    reconcile_stale = _ops.reconcile_stale
    release_clean = _ops.release_clean
    get = _ops.get
    list_records = _ops.list_records
    has_unresolved_owner = _ops.has_unresolved_owner
    get_foreign_recovery = _ops.get_foreign_recovery
    refresh_orphaned_foreign_document_identity = (
        _ops.refresh_orphaned_foreign_document_identity
    )
    list_foreign_recoveries = _ops.list_foreign_recoveries
    _coordination_lost_status = _ops._coordination_lost_status
    _effective_error_at = _ops._effective_error_at
    _clear_effective_error_times = _ops._clear_effective_error_times
    _effective_public_record = _ops._effective_public_record
    _effective_foreign_public = _ops._effective_foreign_public
    get_effective = _ops.get_effective
    list_effective_records = _ops.list_effective_records
