"""Authoritative in-process registry for version-2 document leases."""

from __future__ import annotations

import contextlib
import hashlib
import os
import secrets
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors.authorization_error import AuthorizationError
from .errors.cancellation_context import _CancellationContext
from .errors.clean_release_error import CleanReleaseError
from .errors.coordination_error import CoordinationError
from .errors.dirty_acquisition_error import DirtyAcquisitionError
from .errors.dirty_adoption_error import DirtyAdoptionError
from .errors.document_identity_refresh_event import DocumentIdentityRefreshEvent
from .errors.foreign_recovery_error import ForeignRecoveryError
from .errors.foreign_recovery_record import ForeignRecoveryRecord
from .errors.lease_conflict_error import LeaseConflictError
from .errors.lease_grant import LeaseGrant
from .errors.lease_service_error import LeaseServiceError
from .errors.lease_state_error import LeaseStateError
from .errors.live_document_validation_error import LiveDocumentValidationError
from .errors.local_recovery_error import LocalRecoveryError
from .errors.local_runtime_identity import LocalRuntimeIdentity
from .errors.locked_error_handoff_required import LockedErrorHandoffRequired
from .errors.orphaned_foreign_recovery_required import OrphanedForeignRecoveryRequired
from .errors.orphaned_local_mcp_recovery_required import OrphanedLocalMcpRecoveryRequired
from .errors.process_liveness_evidence import ProcessLivenessEvidence
from .errors.saved_foreign_recovery_required import SavedForeignRecoveryRequired
from .identity import (
    DocumentIdentityError,
    DocumentIdentityService,
    canonicalize_path,
    capture_file_baseline,
    file_identity_for_path,
)
from .model import (
    DocumentIdentity,
    DocumentSelector,
    FileBaseline,
    FileIdentity,
    LeaseCredential,
    LeaseErrorInfo,
    LeaseOwner,
    LeaseRecord,
    LeaseState,
    LiveDocumentValidation,
    SaveAsMigration,
    SaveAsMigrationRole,
    token_fingerprint,
    token_matches,
    utc_now,
)
from .sidecar import (
    SidecarCommitUncertainError,
    SidecarError,
    SidecarStore,
    sidecar_path_for,
)

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 10.0
DEFAULT_SIDECAR_HEARTBEAT_INTERVAL_SECONDS = 30.0
DEFAULT_STALE_AFTER_SECONDS = 90.0
# MCP runtime identity currently records a timestamp produced *inside* the
# process, which may be later than its OS creation time. A probed process that
# started materially after that marker must therefore be a PID reuse. The
# tolerance keeps small timestamp/precision differences fail-closed.
MCP_PROCESS_START_FUTURE_TOLERANCE_SECONDS = 1.0


_IDENTITY_REFRESHABLE_STATES = frozenset(
    {
        LeaseState.ACQUIRING,
        LeaseState.LOCKED_IDLE,
        LeaseState.LOCKED_EDITING,
        LeaseState.LOCKED_RECOMPUTING,
        LeaseState.LOCKED_SAVING,
        LeaseState.LOCKED_ERROR,
        LeaseState.STALE,
        LeaseState.USER_INTERVENED,
        LeaseState.UNLOCKED_DIRTY,
    }
)

_RECOVERY_IDENTITY_REFRESHABLE_STATES = frozenset(
    {
        LeaseState.USER_INTERVENED,
        LeaseState.UNLOCKED_DIRTY,
    }
)


_OWNER_AUTHORIZABLE_STATES = frozenset(
    {
        LeaseState.LOCKED_IDLE,
        LeaseState.LOCKED_EDITING,
        LeaseState.LOCKED_RECOMPUTING,
        LeaseState.LOCKED_SAVING,
        LeaseState.LOCKED_ERROR,
    }
)


def _bounded_text(value: str | None, limit: int) -> str:
    if not value:
        return ""
    clean = "".join(ch if ord(ch) >= 32 else " " for ch in str(value)).strip()
    return clean[:limit]


def _bounded_diagnostic(
    value: str | None,
    limit: int,
    *,
    secrets_to_remove: Iterable[str] = (),
) -> str:
    """Bound display metadata after removing exact bearer credentials."""

    if not value:
        return ""
    clean = "".join(ch if ord(ch) >= 32 else " " for ch in str(value)).strip()
    for secret in (str(item) for item in secrets_to_remove):
        if not secret:
            continue
        clean = clean.replace(secret, "<redacted>")
        clean = clean.replace(token_fingerprint(secret), "<redacted>")
    return clean[:limit]


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
        # Process-local map: document session -> acquisition request id that
        # published the current ACQUIRING reservation. Not persisted in sidecars.
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

    @staticmethod
    def _sidecar_path(record: LeaseRecord) -> Path | None:
        if not record.document.canonical_path:
            return None
        return sidecar_path_for(record.document.canonical_path)

    @staticmethod
    def _authority_equal(left: LeaseRecord, right: LeaseRecord) -> bool:
        return (
            left.lease_id == right.lease_id
            and left.generation == right.generation
            and left.token_fingerprint == right.token_fingerprint
            and left.record_revision == right.record_revision
            and left.state == right.state
            and left.state_revision == right.state_revision
            and left.document.session_uuid == right.document.session_uuid
            and left.document.comparison_key == right.document.comparison_key
            and left.migration == right.migration
        )

    def _assert_sidecar_matches(self, record: LeaseRecord) -> None:
        path = self._sidecar_path(record)
        if path is None:
            return
        try:
            persisted = self.sidecar_store.read(path)
        except SidecarError as exc:
            raise CoordinationError(
                f"document sidecar is unavailable or invalid: {exc}"
            ) from exc
        if not self._authority_equal(record, persisted):
            raise CoordinationError("registry and sidecar authority do not match")

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

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        return parsed if parsed.tzinfo is not None else None

    def _prove_foreign_owner_dead(self, owner: LeaseOwner) -> str:
        """Return bounded proof text, or fail closed when death is uncertain."""

        local = self._local_runtime_identity
        if local is None:
            raise ForeignRecoveryError("local runtime identity evidence is unavailable")
        if (
            not local.addon_profile_id
            or not local.addon_runtime_id
            or local.freecad_pid < 1
            or not local.freecad_process_started_at
        ):
            raise ForeignRecoveryError("local runtime identity evidence is incomplete")
        try:
            uuid.UUID(local.addon_profile_id)
            uuid.UUID(local.addon_runtime_id)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ForeignRecoveryError(
                "local addon profile/runtime identity is invalid"
            ) from exc
        local_started = self._parse_timestamp(local.freecad_process_started_at)
        owner_started = self._parse_timestamp(owner.freecad_process_started_at)
        if local_started is None or owner_started is None:
            raise ForeignRecoveryError(
                "FreeCAD process-start identity evidence is invalid"
            )
        if not local.hostname or not owner.hostname:
            raise ForeignRecoveryError("same-host ownership cannot be proven")
        if local.hostname.casefold() != owner.hostname.casefold():
            raise ForeignRecoveryError(
                "foreign owner belongs to another host; local death is unprovable"
            )
        if not local.boot_id or not owner.boot_id:
            raise ForeignRecoveryError("host boot identity evidence is incomplete")
        if local.boot_id != owner.boot_id:
            return "same host restarted since the recorded owner runtime"

        if local.freecad_pid == owner.freecad_pid:
            if local_started != owner_started:
                return "recorded FreeCAD PID was reused after its owner exited"
            if local.addon_runtime_id != owner.addon_runtime_id:
                return "recorded addon runtime was replaced in the same process"
            raise ForeignRecoveryError(
                "the foreign record identifies the current live addon runtime"
            )

        probe = self._process_liveness_probe
        if probe is None:
            raise ForeignRecoveryError(
                "same-boot process liveness evidence is unavailable"
            )
        try:
            evidence = probe(owner.freecad_pid)
        except Exception as exc:
            raise ForeignRecoveryError(
                f"owner process liveness could not be established: {exc}"
            ) from exc
        if not isinstance(evidence, ProcessLivenessEvidence):
            raise ForeignRecoveryError("owner process probe returned invalid evidence")
        if evidence.exists is False:
            return "recorded FreeCAD process no longer exists on this boot"
        if evidence.exists is None:
            raise ForeignRecoveryError("owner process liveness is unknown")
        if not evidence.process_started_at:
            raise ForeignRecoveryError(
                "live owner process start identity is unavailable"
            )
        evidence_started = self._parse_timestamp(evidence.process_started_at)
        if evidence_started is None:
            raise ForeignRecoveryError("live owner process start identity is invalid")
        if evidence_started == owner_started:
            raise ForeignRecoveryError(
                "the recorded FreeCAD owner process is still alive"
            )
        return "recorded FreeCAD PID now belongs to a different process"

    def _prove_local_mcp_owner_dead(self, owner: LeaseOwner) -> str:
        """Prove that a lease in this addon runtime lost its MCP process.

        The addon/FreeCAD process is intentionally *not* the lease owner. Its
        continued liveness cannot keep authority renewable after the private
        credential-owning MCP process exits. Proof is fail-closed and uses the
        recorded PID together with process-start identity to avoid confusing a
        reused PID with the original owner.
        """

        local = self._local_runtime_identity
        if local is None:
            raise LocalRecoveryError("local runtime identity evidence is unavailable")
        expected_runtime = (
            local.addon_profile_id,
            local.addon_runtime_id,
            local.freecad_pid,
            local.freecad_process_started_at,
            local.boot_id,
        )
        recorded_runtime = (
            owner.addon_profile_id,
            owner.addon_runtime_id,
            owner.freecad_pid,
            owner.freecad_process_started_at,
            owner.boot_id,
        )
        if recorded_runtime != expected_runtime:
            raise LocalRecoveryError(
                "lease authority does not belong to this FreeCAD runtime"
            )
        if (
            not local.hostname
            or not owner.hostname
            or local.hostname.casefold() != owner.hostname.casefold()
        ):
            raise LocalRecoveryError(
                "the lease does not belong to this FreeCAD host"
            )
        if (
            not owner.mcp_hostname
            or owner.mcp_hostname.casefold() != local.hostname.casefold()
        ):
            raise LocalRecoveryError(
                "the credential-owning MCP process is not proven co-located"
            )
        if owner.mcp_pid < 1 or not owner.mcp_process_started_at:
            raise LocalRecoveryError("MCP process identity evidence is incomplete")
        owner_started = self._parse_timestamp(owner.mcp_process_started_at)
        if owner_started is None:
            raise LocalRecoveryError("MCP process-start identity evidence is invalid")
        probe = self._process_liveness_probe
        if probe is None:
            raise LocalRecoveryError("MCP process liveness evidence is unavailable")
        try:
            evidence = probe(owner.mcp_pid)
        except Exception as exc:
            raise LocalRecoveryError(
                f"MCP process liveness could not be established: {exc}"
            ) from exc
        if not isinstance(evidence, ProcessLivenessEvidence):
            raise LocalRecoveryError("MCP process probe returned invalid evidence")
        if evidence.exists is False:
            return "recorded MCP process no longer exists on this boot"
        if evidence.exists is None:
            raise LocalRecoveryError("MCP process liveness is unknown")
        if not evidence.process_started_at:
            raise LocalRecoveryError(
                "live MCP process start identity is unavailable"
            )
        evidence_started = self._parse_timestamp(evidence.process_started_at)
        if evidence_started is None:
            raise LocalRecoveryError("live MCP process start identity is invalid")
        seconds_after_owner_marker = (
            evidence_started - owner_started
        ).total_seconds()
        if seconds_after_owner_marker > MCP_PROCESS_START_FUTURE_TOLERANCE_SECONDS:
            return "recorded MCP PID now belongs to a different process"
        # The current client records module-import time, not exact OS creation
        # time, so an earlier probed start remains compatible with the original
        # live process even when the timestamps differ substantially.
        raise LocalRecoveryError(
            "the credential-owning MCP process may still be alive"
        )

    def _prove_local_mcp_recovery_authority_inactive(
        self,
        record: LeaseRecord,
    ) -> str:
        """Prove that the prior credential cannot race a guarded recovery."""

        if self._is_misattributed_worker_snapshot_intervention(record):
            # Local takeover rotates both generation and token digest using a
            # discarded secret. The narrowly recognized legacy worker snapshot
            # false-positive therefore has no credential that can race, even
            # when its pre-fix record lacks MCP-host evidence.
            return (
                "previous credential was irrevocably fenced after a "
                "misattributed worker snapshot"
            )
        return self._prove_local_mcp_owner_dead(record.owner)

    @staticmethod
    def _is_misattributed_worker_snapshot_intervention(
        record: LeaseRecord,
    ) -> bool:
        """Recognize the pre-fix worker ``saveCopy`` observer signature."""

        if (
            record.state != LeaseState.USER_INTERVENED
            or not record.user_intervened
            or record.error is None
            or record.error.code != "USER_INTERVENED"
        ):
            return False
        message = str(record.error.message or "").replace("\\", "/").casefold()
        prefix = "unscoped freecad save detected:"
        if not message.startswith(prefix):
            return False
        target = message[len(prefix) :].strip()
        filename = target.rsplit("/", 1)[-1]
        sequence, separator, remainder = filename.partition("_")
        return bool(
            "freecad_mcp_workers/" in target
            and "/snapshots/" in target
            and separator
            and len(sequence) == 4
            and sequence.isdigit()
            and remainder.endswith(".fcstd")
        )

    def _prove_orphaned_foreign_authority_inactive(
        self, foreign: ForeignRecoveryRecord
    ) -> str:
        """Prove no credential can still drive the imported authority.

        Most records use the normal same-host process/runtime death proof. A
        missing sidecar can also strand a record created by this exact addon
        runtime after its original document session was replaced. In that
        case, the old session's absence from both identity and lease registries
        is stronger authorization evidence than a PID probe: credentials for
        that UUID cannot pass this service's registry fence.
        """

        try:
            return self._prove_foreign_owner_dead(foreign.persisted.owner)
        except ForeignRecoveryError as original_error:
            local = self._local_runtime_identity
            owner = foreign.persisted.owner
            same_runtime = bool(
                local is not None
                and local.addon_profile_id == owner.addon_profile_id
                and local.addon_runtime_id == owner.addon_runtime_id
                and local.freecad_pid == owner.freecad_pid
                and local.freecad_process_started_at == owner.freecad_process_started_at
                and local.boot_id == owner.boot_id
                and local.hostname
                and owner.hostname
                and local.hostname.casefold() == owner.hostname.casefold()
            )
            foreign_session = foreign.persisted.document.session_uuid
            local_session = foreign.local_document.session_uuid
            if not same_runtime or foreign_session == local_session:
                raise original_error
            if (
                foreign_session in self._records
                or foreign_session in self._pending_save_as
                or foreign_session in self._foreign_records
            ):
                raise original_error
            try:
                self.identity_service.resolve(foreign_session)
            except Exception:
                return (
                    "recorded document session is no longer registered in the "
                    "current addon runtime"
                )
            raise original_error

    @staticmethod
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

    @classmethod
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
            and record.last_verified_save_revision
            == record.last_mutation_revision
            and record.migration is None
        )
        return bool(
            cls._is_clean_orphaned_foreign_candidate(record)
            or legacy_worker_snapshot
        )

    @staticmethod
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
            and record.last_verified_save_revision
            == record.last_mutation_revision
            and record.migration is None
        )

    @staticmethod
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

    @staticmethod
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

    def _assert_current_baseline(
        self,
        identity: DocumentIdentity,
        baseline: FileBaseline,
        *,
        error_type: type[LeaseServiceError] = CoordinationError,
    ) -> None:
        """Revalidate lightweight file metadata after an off-lock hash."""

        path = identity.canonical_path
        if not path or not os.path.isfile(path):
            raise error_type(
                "the saved document path is missing or is not a regular file"
            )
        try:
            info = os.stat(path)
            current_identity = file_identity_for_path(
                path, platform=self.identity_service.platform
            )
        except (DocumentIdentityError, OSError) as exc:
            raise error_type(
                f"the saved document identity cannot be revalidated: {exc}"
            ) from exc
        failures = []
        if int(info.st_size) != baseline.size:
            failures.append("size changed")
        if int(info.st_mtime_ns) != baseline.mtime_ns:
            failures.append("modification time changed")
        if current_identity != baseline.file_identity:
            failures.append("file identity changed")
        if current_identity != identity.file_identity:
            failures.append("registered document identity changed")
        if failures:
            raise error_type(
                "the saved document changed during orphan recovery: "
                + "; ".join(failures)
            )

    def _assert_on_disk_matches_accepted_baseline(
        self,
        path: str,
        baseline: FileBaseline,
        *,
        error_type: type[LeaseServiceError] = CoordinationError,
        allow_file_identity_change: bool = False,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        """Require the saved file to still match the lease's accepted baseline."""

        if not os.path.isfile(path):
            raise error_type(
                "the saved document path is missing or is not a regular file"
            )
        try:
            info = os.stat(path)
            current_identity = file_identity_for_path(
                path, platform=self.identity_service.platform
            )
        except (DocumentIdentityError, OSError) as exc:
            raise error_type(
                f"the saved document identity cannot be revalidated: {exc}"
            ) from exc
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
        sha256 = digest.hexdigest()
        failures: list[str] = []
        if int(info.st_size) != baseline.size:
            failures.append("size changed")
        # Atomic replace-over-save rewrites the file at the same path and
        # changes mtime while size and SHA-256 stay identical.  Content
        # continuity for baseline-preserving identity repair is proven by
        # size + SHA-256, not exact mtime_ns equality.
        if not allow_file_identity_change and int(info.st_mtime_ns) != baseline.mtime_ns:
            failures.append("modification time changed")
        if sha256 != baseline.sha256:
            failures.append("content hash changed")
        if (
            not allow_file_identity_change
            and baseline.file_identity is not None
            and current_identity != baseline.file_identity
        ):
            failures.append("file identity changed")
        if failures:
            raise error_type(
                "the saved document no longer matches the accepted baseline: "
                + "; ".join(failures)
            )

    def _record_identity_refresh_event(
        self,
        record: LeaseRecord,
        *,
        trigger: str,
        previous_file_identity: FileIdentity | None,
        refreshed_file_identity: FileIdentity | None,
    ) -> None:
        baseline = record.baseline
        baseline_sha256 = baseline.sha256 if isinstance(baseline, FileBaseline) else ""
        self._identity_refresh_events.append(
            DocumentIdentityRefreshEvent(
                at=self._utc_clock(),
                trigger=_bounded_text(trigger, 128),
                document_session_uuid=record.document.session_uuid,
                document_name=record.document.name,
                canonical_path=record.document.canonical_path,
                lease_state=record.state.value,
                lease_id=record.lease_id,
                generation=record.generation,
                previous_file_identity=(
                    previous_file_identity.to_dict()
                    if previous_file_identity is not None
                    else None
                ),
                refreshed_file_identity=(
                    refreshed_file_identity.to_dict()
                    if refreshed_file_identity is not None
                    else None
                ),
                baseline_sha256=baseline_sha256,
            )
        )

    def _refresh_exact_proxy_file_identity(
        self,
        session_uuid: str,
        document: Any,
        record: LeaseRecord,
        *,
        trigger: str,
    ) -> LeaseRecord:
        """Refresh file identity metadata without revalidating file content."""

        if record.state not in _RECOVERY_IDENTITY_REFRESHABLE_STATES:
            raise LeaseStateError(
                "saved-file identity can refresh only after takeover",
                details={"state": record.state.value},
            )
        self._assert_sidecar_matches(record)
        observed = self.identity_service.inspect_registered_document(
            session_uuid, document
        )
        expected = record.document
        if observed.name != expected.name or observed.comparison_key != expected.comparison_key:
            raise CoordinationError(
                "GUI save changed the document name or canonical path"
            )
        if observed.file_identity == expected.file_identity:
            return record
        refreshed = self.identity_service.refresh_saved_document(document)
        if refreshed.session_uuid != session_uuid:
            raise CoordinationError(
                "saved document identity changed its live session"
            )
        if refreshed == record.document:
            return record
        updated = record.revised(document=refreshed)
        committed = self._commit(record, updated)
        self._record_identity_refresh_event(
            committed,
            trigger=trigger,
            previous_file_identity=expected.file_identity,
            refreshed_file_identity=refreshed.file_identity,
        )
        return committed

    def _apply_baseline_preserving_identity_refresh(
        self,
        session_uuid: str,
        document: Any,
        record: LeaseRecord,
        *,
        trigger: str,
    ) -> LeaseRecord:
        """Refresh registry and lease metadata after a baseline-preserving save."""

        if record.state not in _IDENTITY_REFRESHABLE_STATES:
            raise LeaseStateError(
                "saved-file identity cannot refresh in the current lease state",
                details={"state": record.state.value},
            )
        self._assert_sidecar_matches(record)
        baseline = record.baseline
        if not isinstance(baseline, FileBaseline):
            raise CoordinationError("accepted saved-file baseline is missing")
        observed = self.identity_service.inspect_registered_document(
            session_uuid, document
        )
        expected = record.document
        if observed.name != expected.name or observed.comparison_key != expected.comparison_key:
            raise CoordinationError(
                "GUI save changed the document name or canonical path"
            )
        path = observed.canonical_path
        if not path:
            raise CoordinationError(
                "an unsaved document has no saved-file identity to refresh"
            )
        if observed.file_identity == expected.file_identity:
            return record
        self._assert_on_disk_matches_accepted_baseline(
            path,
            baseline,
            allow_file_identity_change=True,
        )
        refreshed = self.identity_service.refresh_saved_document(document)
        if refreshed.session_uuid != session_uuid:
            raise CoordinationError(
                "saved document identity changed its live session"
            )
        if (
            refreshed.name != observed.name
            or refreshed.comparison_key != observed.comparison_key
            or refreshed.file_identity != observed.file_identity
        ):
            raise CoordinationError(
                "saved document identity refresh changed the live document binding"
            )
        if refreshed == record.document:
            return record
        post_rewrite_mtime_ns = int(os.stat(path).st_mtime_ns)
        refreshed_baseline = replace(
            baseline,
            file_identity=refreshed.file_identity,
            mtime_ns=post_rewrite_mtime_ns,
        )
        updated = record.revised(document=refreshed, baseline=refreshed_baseline)
        committed = self._commit(record, updated)
        self._record_identity_refresh_event(
            committed,
            trigger=trigger,
            previous_file_identity=expected.file_identity,
            refreshed_file_identity=refreshed.file_identity,
        )
        return committed

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

    def repair_registered_document_identity(
        self, *, document: Any
    ) -> DocumentIdentity:
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
            return self.identity_service.inspect_registered_document(
                session_uuid, document
            )

    def _validate_live_evidence(
        self,
        record: LeaseRecord,
        validation: LiveDocumentValidation,
    ) -> None:
        """Require fresh document and file evidence to match lease authority."""

        if not isinstance(validation, LiveDocumentValidation):
            raise LiveDocumentValidationError(
                "fresh LiveDocumentValidation evidence is required"
            )

        failures: list[str] = []
        expected = record.document
        live = validation.document
        try:
            registered = self.identity_service.resolve(expected.session_uuid)
        except Exception as exc:
            raise LiveDocumentValidationError(
                "the leased document is no longer registered as open",
                details={"reason": str(exc)},
            ) from exc

        if registered.session_uuid != expected.session_uuid:
            failures.append("registered document session changed")
        if registered.comparison_key != expected.comparison_key:
            failures.append("registered document path changed")
        if registered.file_identity != expected.file_identity:
            failures.append("registered document file identity changed")
        if live.session_uuid != expected.session_uuid:
            failures.append("live document session changed")

        if live.canonical_path:
            try:
                _canonical, comparison = canonicalize_path(
                    live.canonical_path, platform=self.identity_service.platform
                )
            except Exception:
                failures.append("live document path is invalid")
            else:
                if comparison != live.comparison_key:
                    failures.append("live document comparison key is inconsistent")
        elif live.comparison_key is not None:
            failures.append("live document path identity is incomplete")

        if live.comparison_key != expected.comparison_key:
            failures.append("live document path changed")
        if live.file_identity != expected.file_identity:
            failures.append("live document file identity changed")
        if not validation.baseline_validated:
            failures.append("current file/snapshot baseline was not validated")

        current_baseline = validation.baseline
        expected_baseline = record.baseline
        if current_baseline != expected_baseline:
            if expected_baseline is None or current_baseline is None:
                failures.append("saved file baseline is missing or newly present")
            else:
                if current_baseline.file_identity != expected_baseline.file_identity:
                    failures.append("saved file identity changed")
                if current_baseline.size != expected_baseline.size:
                    failures.append("saved file size changed")
                if current_baseline.mtime_ns != expected_baseline.mtime_ns:
                    failures.append("saved file modification time changed")
                if current_baseline.sha256 != expected_baseline.sha256:
                    failures.append("saved file hash changed")

        if current_baseline is not None:
            if live.canonical_path is None:
                failures.append("a file baseline was supplied for an unsaved document")
            if current_baseline.file_identity != live.file_identity:
                failures.append("baseline and live document file identities disagree")
        elif live.canonical_path is not None:
            failures.append("saved live document has no current file baseline")

        if failures:
            # Preserve order while keeping structured diagnostics bounded.
            unique_failures = list(dict.fromkeys(failures))
            raise LiveDocumentValidationError(
                "; ".join(unique_failures),
                details={"failures": unique_failures},
            )

    def _commit(self, current: LeaseRecord, updated: LeaseRecord) -> LeaseRecord:
        """Persist first, then publish the in-memory successor."""

        session_uuid = current.document.session_uuid
        path = self._sidecar_path(current)
        if path is not None:
            try:
                self.sidecar_store.replace(path, updated, expected=current)
            except SidecarError as exc:
                raise CoordinationError(
                    f"unable to persist lease transition: {exc}"
                ) from exc
        self._records[session_uuid] = updated
        return updated

    def _record_for_credential(
        self,
        credential: LeaseCredential,
        *,
        allowed_states: Iterable[LeaseState] = _OWNER_AUTHORIZABLE_STATES,
        selector: DocumentSelector | Mapping[str, Any] | str | None = None,
    ) -> LeaseRecord:
        if not isinstance(credential, LeaseCredential):
            raise AuthorizationError("a complete LeaseCredential is required")
        if (
            not credential.lease_id
            or not credential.document_session_uuid
            or credential.generation < 1
            or not credential.token
            or not credential.mcp_instance_id
        ):
            raise AuthorizationError(
                "lease id, document, generation, token, and authenticated MCP runtime are required"
            )
        record = self._records.get(credential.document_session_uuid)
        if record is None:
            raise AuthorizationError("no active lease exists for this document")
        if selector is not None:
            identity = self.identity_service.resolve(selector)
            if identity.session_uuid != credential.document_session_uuid:
                raise AuthorizationError(
                    "credential does not match the selected document"
                )
        if record.lease_id != credential.lease_id:
            raise AuthorizationError("lease id mismatch")
        if record.generation != credential.generation:
            raise AuthorizationError("lease fencing generation mismatch")
        if record.owner.mcp_instance_id != credential.mcp_instance_id:
            raise AuthorizationError(
                "authenticated MCP runtime does not own this lease"
            )
        if not token_matches(credential.token, record.token_fingerprint):
            raise AuthorizationError("lease token mismatch")
        allowed = frozenset(allowed_states)
        if record.state not in allowed:
            raise LeaseStateError(
                f"state {record.state.value} forbids this operation",
                details={"state": record.state.value},
            )
        self._assert_sidecar_matches(record)
        return record

    def acquire(
        self,
        selector: DocumentSelector | Mapping[str, Any] | str,
        owner: LeaseOwner,
        *,
        task_summary: str = "",
        document_dirty: bool = False,
        baseline: FileBaseline | None = None,
        baseline_validated: bool = False,
        snapshot_id: str | None = None,
    ) -> LeaseGrant:
        """Reserve first, then capture/validate and promote the acquisition."""

        reservation = self.begin_acquisition(
            selector,
            owner,
            task_summary=task_summary,
            document_dirty=document_dirty,
        )
        try:
            observed_baseline = baseline
            observed_validated = bool(baseline_validated)
            path = reservation.record.document.canonical_path
            if path and observed_baseline is None:
                if not os.path.isfile(path):
                    raise LeaseServiceError(
                        "saved document path is missing or is not a regular file"
                    )
                try:
                    observed_baseline = capture_file_baseline(
                        path, platform=self.identity_service.platform
                    )
                except (OSError, DocumentIdentityError) as exc:
                    raise LeaseServiceError(
                        f"unable to capture document baseline: {exc}"
                    ) from exc
                observed_validated = True
            return self.complete_acquisition(
                reservation.credential,
                baseline=observed_baseline,
                baseline_validated=observed_validated,
                snapshot_id=snapshot_id,
            )
        except Exception:
            # No token has escaped and no mutation has begun. Roll back only
            # through an exact CAS; a failed rollback remains visibly locked.
            self.abort_acquisition(reservation.credential)
            raise

    def begin_acquisition(
        self,
        selector: DocumentSelector | Mapping[str, Any] | str,
        owner: LeaseOwner,
        *,
        task_summary: str = "",
        document_dirty: bool = False,
        acquisition_request_id: str | None = None,
        live_acquisition_request_ids: frozenset[str] | None = None,
    ) -> LeaseGrant:
        """Publish ACQUIRING before baseline hashing or snapshot creation."""

        if document_dirty:
            raise DirtyAcquisitionError(
                "a pre-existing dirty document requires local adoption"
            )
        return self._begin_acquisition_record(
            selector,
            owner,
            task_summary=task_summary,
            document_dirty=False,
            replace_unreturned_reservation=True,
            acquisition_request_id=acquisition_request_id,
            live_acquisition_request_ids=live_acquisition_request_ids,
        )

    def begin_dirty_adoption(
        self,
        selector: DocumentSelector | Mapping[str, Any] | str,
        owner: LeaseOwner,
        *,
        task_summary: str = "",
        document_dirty: bool,
        local_confirmation: bool,
        acquisition_request_id: str | None = None,
        live_acquisition_request_ids: frozenset[str] | None = None,
    ) -> LeaseGrant:
        """Reserve a locally confirmed, pre-existing dirty document."""

        if local_confirmation is not True:
            raise DirtyAdoptionError(
                "dirty-document adoption requires explicit local GUI confirmation"
            )
        if document_dirty is not True:
            raise DirtyAdoptionError(
                "dirty-document adoption requires a currently dirty live document"
            )
        return self._begin_acquisition_record(
            selector,
            owner,
            task_summary=task_summary,
            document_dirty=True,
            replace_unreturned_reservation=True,
            acquisition_request_id=acquisition_request_id,
            live_acquisition_request_ids=live_acquisition_request_ids,
        )

    def _begin_acquisition_record(
        self,
        selector: DocumentSelector | Mapping[str, Any] | str,
        owner: LeaseOwner,
        *,
        task_summary: str,
        document_dirty: bool,
        replace_unreturned_reservation: bool = False,
        acquisition_request_id: str | None = None,
        live_acquisition_request_ids: frozenset[str] | None = None,
    ) -> LeaseGrant:
        """Publish one clean acquisition or confirmed dirty-adoption record."""

        identity = self.identity_service.resolve(selector)
        adjacent_path = (
            sidecar_path_for(identity.canonical_path)
            if identity.canonical_path
            else None
        )
        if adjacent_path is not None and os.path.lexists(adjacent_path):
            # Observer discovery normally imports adjacent v2 authority when a
            # document opens. Acquisition repeats that read-only discovery so
            # an already-open document can self-recover after an addon restart
            # or delayed sidecar appearance. Unknown/malformed/mismatched
            # sidecars remain untouched and still fail at atomic create below.
            with self._lock:
                known = bool(
                    identity.session_uuid in self._records
                    or identity.session_uuid in self._foreign_records
                )
            if not known:
                with contextlib.suppress(LeaseServiceError):
                    self.import_adjacent_foreign_recovery(
                        identity.session_uuid,
                        live_document=identity,
                    )
        with self._lock:
            existing = self._records.get(identity.session_uuid)
            if existing is not None:
                if (
                    document_dirty
                    and existing.state == LeaseState.LOCKED_ERROR
                    and existing.dirty
                    and not existing.user_intervened
                ):
                    raise LockedErrorHandoffRequired(
                        "a dirty local LOCKED_ERROR lease requires confirmed "
                        "credential handoff",
                        details=existing.to_public_dict(),
                    )
                if (
                    not document_dirty
                    and existing.owner.mcp_instance_id != owner.mcp_instance_id
                    and self._is_recoverable_local_mcp_orphan_candidate(existing)
                ):
                    try:
                        self._prove_local_mcp_recovery_authority_inactive(
                            existing
                        )
                    except LocalRecoveryError:
                        # A live, unknown, or foreign owner remains an ordinary
                        # exclusive-lease conflict. Never turn incomplete
                        # liveness evidence into takeover authority.
                        pass
                    else:
                        raise OrphanedLocalMcpRecoveryRequired(
                            "a saved local lease has inactive credential "
                            "authority and requires verified in-process fencing",
                            details=existing.to_public_dict(),
                        )
                if replace_unreturned_reservation and self._is_unreturned_reservation(
                    existing,
                    allow_active_acquiring=self._may_fence_local_active_acquiring(
                        existing,
                        owner,
                        session_uuid=identity.session_uuid,
                        live_acquisition_request_ids=live_acquisition_request_ids,
                    ),
                ):
                    return self._replace_unreturned_reservation(
                        existing,
                        identity,
                        owner,
                        task_summary=task_summary,
                        document_dirty=document_dirty,
                        acquisition_request_id=acquisition_request_id,
                    )
                raise LeaseConflictError(
                    "the live document already has a lease",
                    details=existing.to_public_dict(),
                )
            foreign = self._foreign_records.get(identity.session_uuid)
            if foreign is not None:
                foreign_path = (
                    sidecar_path_for(identity.canonical_path)
                    if identity.canonical_path
                    else None
                )
                if (
                    replace_unreturned_reservation
                    and foreign_path is not None
                    and not os.path.lexists(foreign_path)
                    and self._is_missing_sidecar_foreign_recovery_candidate(
                        foreign.persisted
                    )
                ):
                    raise OrphanedForeignRecoveryRequired(
                        "a recoverable foreign record lost its sidecar and "
                        "requires verified in-process fencing",
                        details=foreign.to_public_dict(),
                    )
                if replace_unreturned_reservation and self._is_unreturned_reservation(
                    foreign.persisted,
                    allow_active_acquiring=True,
                ):
                    return self._replace_unreturned_reservation(
                        foreign.persisted,
                        identity,
                        owner,
                        task_summary=task_summary,
                        document_dirty=document_dirty,
                        foreign=foreign,
                        acquisition_request_id=acquisition_request_id,
                    )
                if (
                    foreign_path is not None
                    and os.path.lexists(foreign_path)
                    and (
                        self._is_saved_dirty_foreign_candidate(foreign.persisted)
                        or self._is_abandoned_locked_error_foreign_candidate(
                            foreign.persisted
                        )
                    )
                ):
                    raise SavedForeignRecoveryRequired(
                        "a document is blocked by recoverable dirty authority from "
                        "another runtime and requires verified in-process fencing",
                        details=foreign.to_public_dict(),
                    )
                raise LeaseConflictError(
                    "a foreign recovery record owns the live document",
                    details=foreign.to_public_dict(),
                )
            generation = self._generations.get(identity.session_uuid, 0) + 1
            raw_token = self._token_factory()
            if not raw_token:
                raise LeaseServiceError("token factory returned an empty token")
            now = self._utc_clock()
            now_mono = self._monotonic_ns()
            record = LeaseRecord(
                lease_id=str(self._uuid_factory()),
                generation=generation,
                token_fingerprint=token_fingerprint(raw_token),
                document=identity,
                owner=owner,
                state=LeaseState.ACQUIRING,
                record_revision=1,
                state_revision=1,
                acquired_at=now,
                last_heartbeat_at=now,
                monotonic_heartbeat_ns=now_mono,
                task_summary=_bounded_text(task_summary, 1024),
                dirty=document_dirty,
                last_mutation_revision=1 if document_dirty else 0,
                baseline=None,
                validation_complete=False,
                snapshot_id=None,
            )
            path = self._sidecar_path(record)
            if path is not None:
                try:
                    self.sidecar_store.create(path, record)
                except SidecarError as exc:
                    raise LeaseConflictError(
                        f"document sidecar prevents acquisition: {exc}"
                    ) from exc
            self._records[identity.session_uuid] = record
            self._generations[identity.session_uuid] = generation
            self._last_sidecar_heartbeat_ns[identity.session_uuid] = now_mono
            self._remember_acquiring_request(
                identity.session_uuid, acquisition_request_id
            )
            credential = LeaseCredential(
                lease_id=record.lease_id,
                document_session_uuid=identity.session_uuid,
                generation=generation,
                token=raw_token,
                mcp_instance_id=owner.mcp_instance_id,
            )
            return LeaseGrant(credential=credential, record=record)

    def recover_orphaned_local_mcp_acquisition(
        self,
        selector: DocumentSelector | Mapping[str, Any] | str,
        owner: LeaseOwner,
        *,
        validation: LiveDocumentValidation,
        snapshot_id: str,
        task_summary: str = "",
        authority_handoff: Callable[[LeaseRecord], bool] | None = None,
        authority_rollback: Callable[[], bool] | None = None,
        credential_escrow: Callable[[LeaseGrant], bool] | None = None,
    ) -> LeaseGrant:
        """Atomically acquire a clean document with inactive prior authority.

        The live addon is only the authority registry; it is not lease
        liveness. The caller creates a recovery snapshot under the old core
        fence first. Only then may this method rotate directly to completed
        ``LOCKED_IDLE`` authority after the old process is proven dead or its
        credential is already irrevocably revoked, and fresh GUI/file evidence
        proves that no document state would be lost.
        A snapshot failure therefore leaves the old registry and sidecar
        authority unchanged. When a core-authority handoff callback is
        supplied, the replacement is not published in memory and no credential
        is returned until the sidecar CAS, exact core fence, and optional
        private credential escrow all succeed.
        """

        if (authority_handoff is None) != (authority_rollback is None):
            raise LeaseServiceError(
                "core authority handoff and rollback callbacks must be supplied together"
            )
        if credential_escrow is not None and authority_rollback is None:
            raise LeaseServiceError(
                "credential escrow requires an authority rollback callback"
            )
        identity = self.identity_service.resolve(selector)
        with self._lock:
            current = self._records.get(identity.session_uuid)
            if current is None:
                raise LeaseConflictError(
                    "the selected document has no local lease to recover"
                )
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
                raise CoordinationError(
                    "orphan recovery is blocked during Save As recovery"
                )
            self._assert_sidecar_matches(current)

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
            replacement_runtime = (
                owner.addon_profile_id,
                owner.addon_runtime_id,
                owner.freecad_pid,
                owner.freecad_process_started_at,
                owner.boot_id,
            )
            if replacement_runtime != expected_runtime:
                raise CoordinationError(
                    "replacement owner does not belong to this FreeCAD runtime"
                )
            if (
                not local.hostname
                or not owner.hostname
                or local.hostname.casefold() != owner.hostname.casefold()
            ):
                raise CoordinationError(
                    "replacement owner does not belong to this host"
                )
            self._prove_local_mcp_recovery_authority_inactive(current)

            if not isinstance(validation, LiveDocumentValidation):
                raise LiveDocumentValidationError(
                    "fresh LiveDocumentValidation evidence is required"
                )
            if validation.document != identity:
                raise LiveDocumentValidationError(
                    "live document evidence does not match the registered document"
                )
            if validation.document_modified:
                raise DirtyAcquisitionError(
                    "orphan recovery requires a clean live document"
                )
            if (
                validation.baseline_validated is not True
                or not isinstance(validation.baseline, FileBaseline)
            ):
                raise LiveDocumentValidationError(
                    "orphan recovery requires a validated saved-file baseline"
                )
            if validation.baseline != current.baseline:
                raise LiveDocumentValidationError(
                    "the saved file changed after the orphaned lease was verified"
                )
            self._assert_current_baseline(
                identity,
                validation.baseline,
                error_type=LiveDocumentValidationError,
            )
            try:
                normalized_snapshot = str(uuid.UUID(str(snapshot_id)))
            except (TypeError, ValueError, AttributeError) as exc:
                raise LeaseServiceError(
                    "orphan recovery snapshot ID must be a UUID"
                ) from exc

            raw_token = self._token_factory()
            if not raw_token:
                raise LeaseServiceError("token factory returned an empty token")
            replacement_fingerprint = token_fingerprint(raw_token)
            if secrets.compare_digest(
                replacement_fingerprint,
                current.token_fingerprint,
            ):
                raise LeaseServiceError(
                    "token factory did not rotate the fencing digest"
                )
            generation = (
                max(
                    current.generation,
                    self._generations.get(identity.session_uuid, 0),
                )
                + 1
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
                record_revision=current.record_revision + 1,
                state_revision=current.state_revision + 1,
                acquired_at=now,
                last_heartbeat_at=now,
                monotonic_heartbeat_ns=now_mono,
                heartbeat_sequence=0,
                current_operation="",
                task_summary=_bounded_text(task_summary, 1024),
                dirty=False,
                user_intervened=False,
                last_mutation_revision=0,
                last_successful_save_at=None,
                last_verified_save_revision=0,
                baseline=validation.baseline,
                error=None,
                validation_complete=True,
                snapshot_id=normalized_snapshot,
                migration=None,
            )
            path = self._sidecar_path(current)
            if path is None:
                raise CoordinationError(
                    "local orphan recovery requires a saved document sidecar"
                )

            def exact_persisted_record(
                persisted: LeaseRecord | None,
                proposed: LeaseRecord,
            ) -> bool:
                if persisted is None:
                    return False
                include_task_summary = self.sidecar_store.persist_task_summary
                return persisted.to_sidecar_dict(
                    include_task_summary=include_task_summary
                ) == proposed.to_sidecar_dict(
                    include_task_summary=include_task_summary
                )

            sidecar_commit_uncertain = False
            try:
                self.sidecar_store.replace(path, replacement, expected=current)
            except SidecarCommitUncertainError as exc:
                # os.replace already published. Continue only when a strict
                # read under the same native CAS guard proved that every
                # persisted field is the intended successor. If the strict
                # reread itself was unavailable, continue the core+escrow
                # handoff with an explicit warning: os.replace is known to
                # have published, and stopping here would strand its raw token.
                if exc.persisted is not None and not exact_persisted_record(
                    exc.persisted,
                    replacement,
                ):
                    raise CoordinationError(
                        "local orphan sidecar commit could not be proven",
                        details={
                            "commit_uncertain": True,
                            "retain_snapshot": True,
                        },
                    ) from exc
                sidecar_commit_uncertain = True
            except SidecarError as exc:
                raise CoordinationError(
                    f"local orphan authority could not be fenced: {exc}"
                ) from exc
            except Exception as exc:
                # A non-conforming store/backend error has unknown publication
                # state. Preserve the snapshot rather than treating it as a
                # proven pre-commit failure.
                raise CoordinationError(
                    "local orphan sidecar commit failed with unknown state",
                    details={
                        "commit_uncertain": True,
                        "retain_snapshot": True,
                    },
                ) from exc

            def rollback_cross_layer_commit(
                failure_label: str,
                failure: Exception | None,
            ) -> None:
                sidecar_restored = False
                authority_restored = False
                rollback_commit_uncertain = False
                rollback_messages: list[str] = []
                restored_record = replace(
                    current,
                    record_revision=replacement.record_revision + 1,
                    state_revision=replacement.state_revision + 1,
                )
                try:
                    # Re-publish the prior authority at strictly newer
                    # revisions. Sidecar CAS history never moves backwards,
                    # even when a cross-layer handoff is rolled back.
                    try:
                        self.sidecar_store.replace(
                            path,
                            restored_record,
                            expected=replacement,
                        )
                    except SidecarCommitUncertainError as exc:
                        if not exact_persisted_record(
                            exc.persisted,
                            restored_record,
                        ):
                            raise
                        rollback_commit_uncertain = True
                    sidecar_restored = True
                    self._records[identity.session_uuid] = restored_record
                except Exception as exc:
                    rollback_messages.append(f"sidecar rollback failed: {exc}")
                self._generations[identity.session_uuid] = max(
                    self._generations.get(identity.session_uuid, 0),
                    replacement.generation,
                )
                if authority_rollback is not None:
                    try:
                        authority_restored = bool(authority_rollback())
                    except Exception as exc:
                        authority_restored = False
                        rollback_messages.append(
                            f"core authority rollback raised: {exc}"
                        )
                    if not authority_restored and not any(
                        message.startswith("core authority rollback")
                        for message in rollback_messages
                    ):
                        rollback_messages.append(
                            "core authority rollback could not be verified"
                        )
                detail = (
                    "; ".join(rollback_messages)
                    if rollback_messages
                    else "prior sidecar and core authority were restored"
                )
                error = CoordinationError(
                    failure_label + "; " + detail,
                    details={
                        "failure_stage": failure_label,
                        "sidecar_restored": sidecar_restored,
                        "core_authority_restored": authority_restored,
                        # Any cross-layer disagreement may still require the
                        # newly created recovery artifact for diagnosis or
                        # confirmed recovery.
                        "retain_snapshot": not (
                            sidecar_restored and authority_restored
                        )
                        or rollback_commit_uncertain,
                    },
                )
                if failure is not None:
                    raise error from failure
                raise error

            handoff_error: Exception | None = None
            handoff_complete = True
            if authority_handoff is not None:
                try:
                    handoff_complete = bool(authority_handoff(replacement))
                except Exception as exc:
                    handoff_error = exc
                    handoff_complete = False
            if not handoff_complete:
                rollback_cross_layer_commit(
                    "core mutation authority handoff failed",
                    handoff_error,
                )
            credential = LeaseCredential(
                lease_id=replacement.lease_id,
                document_session_uuid=identity.session_uuid,
                generation=generation,
                token=raw_token,
                mcp_instance_id=owner.mcp_instance_id,
            )
            grant = LeaseGrant(
                credential=credential,
                record=replacement,
                coordination_uncertain=sidecar_commit_uncertain,
            )
            escrow_error: Exception | None = None
            escrow_complete = True
            if credential_escrow is not None:
                try:
                    escrow_complete = bool(credential_escrow(grant))
                except Exception as exc:
                    escrow_error = exc
                    escrow_complete = False
            if not escrow_complete:
                rollback_cross_layer_commit(
                    "acquisition credential escrow failed",
                    escrow_error,
                )
            self._records[identity.session_uuid] = replacement
            self._closed_documents.pop(identity.session_uuid, None)
            self._generations[identity.session_uuid] = generation
            self._last_sidecar_heartbeat_ns[identity.session_uuid] = now_mono
            self._clear_effective_error_times(identity.session_uuid)
            self._clear_acquiring_request(identity.session_uuid)
            return grant

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
                raise ForeignRecoveryError(
                    "orphan recovery requires a saved open document"
                )
            if os.path.lexists(path):
                raise CoordinationError(
                    "foreign recovery sidecar reappeared before fencing"
                )
            self._prove_orphaned_foreign_authority_inactive(foreign)
            if not isinstance(validation, LiveDocumentValidation):
                raise LiveDocumentValidationError(
                    "fresh LiveDocumentValidation evidence is required"
                )
            if validation.document != identity:
                raise LiveDocumentValidationError(
                    "live document evidence does not match the registered document"
                )
            if validation.document_modified:
                raise DirtyAcquisitionError(
                    "a pre-existing dirty document requires local adoption"
                )
            if validation.baseline_validated is not True:
                raise LiveDocumentValidationError(
                    "orphan recovery requires a validated saved-file baseline"
                )
            if not isinstance(validation.baseline, FileBaseline):
                raise LiveDocumentValidationError(
                    "orphan recovery requires a saved-file baseline"
                )
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
                task_summary=_bounded_text(task_summary, 1024),
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

    def recover_orphaned_foreign_acquisition(
        self,
        selector: DocumentSelector | Mapping[str, Any] | str,
        owner: LeaseOwner,
        *,
        validation: LiveDocumentValidation,
        snapshot_id: str,
        task_summary: str = "",
        adopt_dirty: bool = False,
        local_confirmation: bool = False,
        authority_handoff: Callable[[LeaseRecord], bool] | None = None,
        authority_rollback: Callable[[], bool] | None = None,
        credential_escrow: Callable[[LeaseGrant], bool] | None = None,
    ) -> LeaseGrant:
        """Recover cached foreign authority after its sidecar disappeared.

        The caller first snapshots the exact live document under the existing
        core fence. This method then revalidates the cached saved baseline,
        proves the recorded foreign FreeCAD authority inactive, atomically
        creates completed replacement authority, verifies the core handoff,
        and escrows the only raw credential before publishing it in memory.

        Dirty live state is never inferred clean. It requires the normal local
        adoption confirmation and is retained in both the replacement lease and
        recovery snapshot. A sidecar that reappears wins the atomic-create race.
        """

        if (authority_handoff is None) != (authority_rollback is None):
            raise LeaseServiceError(
                "core authority handoff and rollback callbacks must be supplied together"
            )
        if credential_escrow is not None and authority_rollback is None:
            raise LeaseServiceError(
                "credential escrow requires an authority rollback callback"
            )
        if adopt_dirty and local_confirmation is not True:
            raise DirtyAdoptionError(
                "dirty-document recovery requires explicit local GUI confirmation"
            )

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
            if not self._is_missing_sidecar_foreign_recovery_candidate(previous):
                raise ForeignRecoveryError(
                    "foreign authority lacks a verified recoverable saved baseline"
                )
            if identity.session_uuid in self._pending_save_as:
                raise CoordinationError(
                    "orphan recovery is blocked during Save As recovery"
                )

            path = (
                sidecar_path_for(identity.canonical_path)
                if identity.canonical_path
                else None
            )
            if path is None:
                raise ForeignRecoveryError(
                    "orphan recovery requires a saved open document"
                )
            if os.path.lexists(path):
                raise CoordinationError(
                    "foreign recovery sidecar reappeared before fencing"
                )

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
            replacement_runtime = (
                owner.addon_profile_id,
                owner.addon_runtime_id,
                owner.freecad_pid,
                owner.freecad_process_started_at,
                owner.boot_id,
            )
            if replacement_runtime != expected_runtime:
                raise CoordinationError(
                    "replacement owner does not belong to this FreeCAD runtime"
                )
            if (
                not local.hostname
                or not owner.hostname
                or local.hostname.casefold() != owner.hostname.casefold()
            ):
                raise CoordinationError(
                    "replacement owner does not belong to this host"
                )
            # Imported text is diagnostic data, not authority. Even the exact
            # legacy worker signature must independently prove its recorded
            # foreign FreeCAD process/runtime inactive.
            self._prove_orphaned_foreign_authority_inactive(foreign)

            if not isinstance(validation, LiveDocumentValidation):
                raise LiveDocumentValidationError(
                    "fresh LiveDocumentValidation evidence is required"
                )
            if validation.document != identity:
                raise LiveDocumentValidationError(
                    "live document evidence does not match the registered document"
                )
            if validation.document_modified and not adopt_dirty:
                raise DirtyAcquisitionError(
                    "a pre-existing dirty document requires local adoption"
                )
            if adopt_dirty and not validation.document_modified:
                raise DirtyAdoptionError(
                    "dirty-document recovery requires a currently dirty live document"
                )
            if validation.baseline_validated is not True:
                raise LiveDocumentValidationError(
                    "orphan recovery requires a validated saved-file baseline"
                )
            if not isinstance(validation.baseline, FileBaseline):
                raise LiveDocumentValidationError(
                    "orphan recovery requires a saved-file baseline"
                )
            if validation.baseline != previous.baseline:
                raise LiveDocumentValidationError(
                    "the saved file no longer matches the foreign recovery baseline"
                )
            self._assert_current_baseline(
                identity,
                validation.baseline,
                error_type=LiveDocumentValidationError,
            )
            try:
                normalized_snapshot = str(uuid.UUID(str(snapshot_id)))
            except (TypeError, ValueError, AttributeError) as exc:
                raise LeaseServiceError(
                    "orphan recovery snapshot ID must be a UUID"
                ) from exc

            raw_token = self._token_factory()
            if not raw_token:
                raise LeaseServiceError("token factory returned an empty token")
            replacement_fingerprint = token_fingerprint(raw_token)
            if secrets.compare_digest(
                replacement_fingerprint,
                previous.token_fingerprint,
            ):
                raise LeaseServiceError(
                    "token factory did not rotate the fencing digest"
                )
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
                task_summary=_bounded_text(task_summary, 1024),
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

            def exact_persisted_record(
                persisted: LeaseRecord | None,
                proposed: LeaseRecord,
            ) -> bool:
                if persisted is None:
                    return False
                include_task_summary = self.sidecar_store.persist_task_summary
                return persisted.to_sidecar_dict(
                    include_task_summary=include_task_summary
                ) == proposed.to_sidecar_dict(
                    include_task_summary=include_task_summary
                )

            sidecar_commit_uncertain = False
            try:
                self.sidecar_store.create(path, replacement)
            except SidecarCommitUncertainError as exc:
                # Atomic link publication succeeded. Continue only with the
                # exact successor (or an unavailable guarded reread), then make
                # the raw token recoverable through the private claim vault.
                if exc.persisted is not None and not exact_persisted_record(
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
                sidecar_commit_uncertain = True
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

            def rollback_cross_layer_commit(
                failure_label: str,
                failure: Exception | None,
            ) -> None:
                sidecar_restored = False
                authority_restored = False
                rollback_commit_uncertain = False
                rollback_messages: list[str] = []
                try:
                    try:
                        self.sidecar_store.delete(path, expected=replacement)
                    except SidecarCommitUncertainError as exc:
                        if exc.absent is not True:
                            raise
                        rollback_commit_uncertain = True
                    sidecar_restored = True
                except Exception as exc:
                    rollback_messages.append(f"sidecar rollback failed: {exc}")
                # Never reuse a generation whose token may have crossed a
                # filesystem or core boundary, even when rollback succeeded.
                self._generations[identity.session_uuid] = max(
                    self._generations.get(identity.session_uuid, 0),
                    replacement.generation,
                )
                if authority_rollback is not None:
                    try:
                        authority_restored = bool(authority_rollback())
                    except Exception as exc:
                        authority_restored = False
                        rollback_messages.append(
                            f"core authority rollback raised: {exc}"
                        )
                    if not authority_restored and not any(
                        message.startswith("core authority rollback")
                        for message in rollback_messages
                    ):
                        rollback_messages.append(
                            "core authority rollback could not be verified"
                        )
                detail = (
                    "; ".join(rollback_messages)
                    if rollback_messages
                    else "missing sidecar and prior core authority were restored"
                )
                error = CoordinationError(
                    failure_label + "; " + detail,
                    details={
                        "failure_stage": failure_label,
                        "sidecar_restored": sidecar_restored,
                        "core_authority_restored": authority_restored,
                        "retain_snapshot": not (
                            sidecar_restored and authority_restored
                        )
                        or rollback_commit_uncertain,
                    },
                )
                if failure is not None:
                    raise error from failure
                raise error

            handoff_error: Exception | None = None
            handoff_complete = True
            if authority_handoff is not None:
                try:
                    handoff_complete = bool(authority_handoff(replacement))
                except Exception as exc:
                    handoff_error = exc
                    handoff_complete = False
            if not handoff_complete:
                rollback_cross_layer_commit(
                    "core mutation authority handoff failed",
                    handoff_error,
                )

            credential = LeaseCredential(
                lease_id=replacement.lease_id,
                document_session_uuid=identity.session_uuid,
                generation=generation,
                token=raw_token,
                mcp_instance_id=owner.mcp_instance_id,
            )
            grant = LeaseGrant(
                credential=credential,
                record=replacement,
                coordination_uncertain=sidecar_commit_uncertain,
            )
            escrow_error: Exception | None = None
            escrow_complete = True
            if credential_escrow is not None:
                try:
                    escrow_complete = bool(credential_escrow(grant))
                except Exception as exc:
                    escrow_error = exc
                    escrow_complete = False
            if not escrow_complete:
                rollback_cross_layer_commit(
                    "acquisition credential escrow failed",
                    escrow_error,
                )

            self._records[identity.session_uuid] = replacement
            self._foreign_records.pop(identity.session_uuid, None)
            self._closed_documents.pop(identity.session_uuid, None)
            self._generations[identity.session_uuid] = generation
            self._last_sidecar_heartbeat_ns[identity.session_uuid] = now_mono
            self._clear_effective_error_times(identity.session_uuid)
            self._clear_acquiring_request(identity.session_uuid)
            return grant

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
            abandoned_locked_error = (
                self._is_abandoned_locked_error_foreign_candidate(previous)
            )
            if not acknowledged_dirty and not abandoned_locked_error:
                raise ForeignRecoveryError(
                    "foreign authority is not recoverable dirty authority"
                )
            path = (
                sidecar_path_for(identity.canonical_path)
                if identity.canonical_path
                else None
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
            self._prove_foreign_owner_dead(previous.owner)
            if not isinstance(validation, LiveDocumentValidation):
                raise LiveDocumentValidationError(
                    "fresh LiveDocumentValidation evidence is required"
                )
            if validation.document != identity:
                raise LiveDocumentValidationError(
                    "live document evidence does not match the registered document"
                )
            if validation.document_modified and not adopt_dirty:
                raise DirtyAcquisitionError(
                    "a pre-existing dirty document requires local adoption"
                )
            if validation.document_modified and local_confirmation is not True:
                raise DirtyAdoptionError(
                    "dirty-document recovery requires explicit local GUI confirmation"
                )
            if adopt_dirty and not validation.document_modified:
                raise DirtyAdoptionError(
                    "dirty-document recovery requires a currently dirty live document"
                )
            if validation.baseline_validated is not True:
                raise LiveDocumentValidationError(
                    "saved foreign recovery requires a validated saved-file baseline"
                )
            if not isinstance(validation.baseline, FileBaseline):
                raise LiveDocumentValidationError(
                    "saved foreign recovery requires a saved-file baseline"
                )
            if (
                abandoned_locked_error
                and validation.baseline != previous.baseline
            ):
                raise LiveDocumentValidationError(
                    "the saved file no longer matches the errored lease baseline"
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
                task_summary=_bounded_text(task_summary, 1024),
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
            if identity.session_uuid in self._pending_save_as:
                raise CoordinationError(
                    "credential handoff is blocked during Save As recovery"
                )
            self._assert_sidecar_matches(current)

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
            if (
                validation.baseline_validated is not True
                or not isinstance(validation.baseline, FileBaseline)
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

            raw_token = self._token_factory()
            if not raw_token:
                raise LeaseServiceError("token factory returned an empty token")
            replacement_fingerprint = token_fingerprint(raw_token)
            if secrets.compare_digest(
                replacement_fingerprint,
                current.token_fingerprint,
            ):
                raise LeaseServiceError(
                    "token factory did not rotate the fencing digest"
                )
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
                task_summary=_bounded_text(task_summary, 1024),
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

    def _remember_acquiring_request(
        self, session_uuid: str, acquisition_request_id: str | None
    ) -> None:
        request_id = str(acquisition_request_id or "").strip()
        if request_id:
            self._acquiring_request_ids[session_uuid] = request_id
        else:
            self._acquiring_request_ids.pop(session_uuid, None)

    def _clear_acquiring_request(self, session_uuid: str) -> None:
        self._acquiring_request_ids.pop(session_uuid, None)

    def _may_fence_local_active_acquiring(
        self,
        record: LeaseRecord,
        owner: LeaseOwner,
        *,
        session_uuid: str,
        live_acquisition_request_ids: frozenset[str] | None,
    ) -> bool:
        """Allow fencing of a same-MCP unreturned ACQUIRING reservation.

        Matching ``mcp_instance_id`` alone is not enough: one MCP process may
        have concurrent acquire/adopt requests. Immediate fencing is allowed
        only when the reservation's recorded acquisition request ID is absent
        from the live inflight set (terminal, abandoned, or never tracked).
        """

        existing_owner = str(record.owner.mcp_instance_id or "")
        requesting_owner = str(owner.mcp_instance_id or "")
        if not existing_owner or existing_owner != requesting_owner:
            return False
        recorded = str(self._acquiring_request_ids.get(session_uuid) or "")
        if not recorded:
            # Legacy/unknown publisher: refuse live ACQUIRING fencing; STALE
            # and USER_INTERVENED shapes remain eligible without this flag.
            return False
        live = live_acquisition_request_ids or frozenset()
        return recorded not in live

    @staticmethod
    def _is_unreturned_reservation(
        record: LeaseRecord,
        *,
        allow_active_acquiring: bool = False,
    ) -> bool:
        """Recognize a fenced reservation that never reached promotion.

        This narrow shape excludes every lease that could contain agent edits or
        a completed recovery snapshot. A clean acquisition or a freshly confirmed
        dirty adoption may therefore fence it without losing recovery authority.

        Active ``ACQUIRING`` is only treated as unreturned when the caller opts
        in via ``allow_active_acquiring`` after proving ownership/runtime safety
        (same MCP instance with a non-live acquisition request id locally, or
        dead FreeCAD owner for foreign records).
        """

        acquiring = (
            allow_active_acquiring
            and record.state == LeaseState.ACQUIRING
            and not record.user_intervened
            and record.error is None
        )
        stale = (
            record.state == LeaseState.STALE
            and not record.user_intervened
            and record.error is not None
            and record.error.code == "LEASE_STALE"
        )
        intervened = (
            record.state == LeaseState.USER_INTERVENED
            and record.user_intervened
            and record.error is not None
            and record.error.code == "USER_INTERVENED"
        )
        return bool(
            (acquiring or stale or intervened)
            and record.document.canonical_path is not None
            and record.last_mutation_revision in {0, 1}
            and record.last_verified_save_revision == 0
            and record.last_successful_save_at is None
            and record.baseline is None
            and not record.validation_complete
            and record.snapshot_id is None
            and record.migration is None
        )

    def _replace_unreturned_reservation(
        self,
        previous: LeaseRecord,
        identity: DocumentIdentity,
        owner: LeaseOwner,
        *,
        task_summary: str,
        document_dirty: bool,
        foreign: ForeignRecoveryRecord | None = None,
        acquisition_request_id: str | None = None,
    ) -> LeaseGrant:
        """CAS-fence one local/foreign reservation whose credential was not returned."""

        if foreign is not None:
            if foreign.local_document != identity or foreign.persisted != previous:
                raise CoordinationError(
                    "the imported foreign recovery authority changed"
                )
            path = sidecar_path_for(identity.canonical_path)
            try:
                persisted = self.sidecar_store.read(path)
            except SidecarError as exc:
                raise CoordinationError(
                    f"foreign acquisition sidecar is unavailable or invalid: {exc}"
                ) from exc
            if persisted != previous:
                raise CoordinationError(
                    "foreign acquisition authority changed after import"
                )
            self._assert_foreign_document_exact(
                identity,
                persisted,
                allow_unreturned_file_replacement=True,
            )
            self._prove_foreign_owner_dead(persisted.owner)

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
            task_summary=_bounded_text(task_summary, 1024),
            dirty=document_dirty,
            last_mutation_revision=1 if document_dirty else 0,
            baseline=None,
            validation_complete=False,
            snapshot_id=None,
        )
        path = self._sidecar_path(previous)
        if path is not None:
            try:
                self.sidecar_store.replace(path, replacement, expected=previous)
            except SidecarError as exc:
                raise CoordinationError(
                    f"unreturned acquisition reservation could not be fenced: {exc}"
                ) from exc
        self._records[identity.session_uuid] = replacement
        self._foreign_records.pop(identity.session_uuid, None)
        self._closed_documents.pop(identity.session_uuid, None)
        self._generations[identity.session_uuid] = generation
        self._last_sidecar_heartbeat_ns[identity.session_uuid] = now_mono
        self._remember_acquiring_request(
            identity.session_uuid, acquisition_request_id
        )
        credential = LeaseCredential(
            lease_id=replacement.lease_id,
            document_session_uuid=identity.session_uuid,
            generation=generation,
            token=raw_token,
            mcp_instance_id=owner.mcp_instance_id,
        )
        return LeaseGrant(credential=credential, record=replacement)

    def complete_dirty_adoption(
        self,
        credential: LeaseCredential,
        *,
        baseline: FileBaseline,
        baseline_validated: bool,
        snapshot_id: str,
    ) -> LeaseGrant:
        """Promote only an ACQUIRING record created for dirty adoption."""

        return self._complete_acquisition_record(
            credential,
            baseline=baseline,
            baseline_validated=baseline_validated,
            snapshot_id=snapshot_id,
            expected_dirty=True,
        )

    def record_acquisition_snapshot(
        self,
        credential: LeaseCredential,
        *,
        snapshot_id: str,
    ) -> LeaseRecord:
        """Persist recovery-snapshot authority before acquisition promotion."""

        try:
            normalized_snapshot = str(uuid.UUID(str(snapshot_id)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise LeaseServiceError("acquisition snapshot ID must be a UUID") from exc
        with self._lock:
            record = self._record_for_credential(
                credential,
                allowed_states={LeaseState.ACQUIRING},
            )
            if record.snapshot_id is not None:
                if record.snapshot_id != normalized_snapshot:
                    raise CoordinationError(
                        "acquisition snapshot authority already changed"
                    )
                return record
            updated = record.revised(snapshot_id=normalized_snapshot)
            return self._commit(record, updated)

    def complete_acquisition(
        self,
        credential: LeaseCredential,
        *,
        baseline: FileBaseline | None,
        baseline_validated: bool,
        snapshot_id: str | None,
    ) -> LeaseGrant:
        """Promote only an exact clean reservation with complete evidence."""

        return self._complete_acquisition_record(
            credential,
            baseline=baseline,
            baseline_validated=baseline_validated,
            snapshot_id=snapshot_id,
            expected_dirty=False,
        )

    def _complete_acquisition_record(
        self,
        credential: LeaseCredential,
        *,
        baseline: FileBaseline | None,
        baseline_validated: bool,
        snapshot_id: str | None,
        expected_dirty: bool,
    ) -> LeaseGrant:
        """Promote one exact reservation with complete saved-file evidence."""

        with self._lock:
            record = self._record_for_credential(
                credential, allowed_states={LeaseState.ACQUIRING}
            )
            if record.dirty != expected_dirty:
                raise DirtyAdoptionError(
                    "the acquisition reservation does not match the requested lifecycle"
                )
            if expected_dirty and record.last_mutation_revision < 1:
                raise DirtyAdoptionError(
                    "dirty adoption has no recorded pre-existing mutation"
                )
            path = record.document.canonical_path
            normalized_snapshot = None
            if snapshot_id:
                try:
                    normalized_snapshot = str(uuid.UUID(str(snapshot_id)))
                except (TypeError, ValueError, AttributeError) as exc:
                    raise LeaseServiceError(
                        "acquisition snapshot ID must be a UUID"
                    ) from exc
            if (
                record.snapshot_id is not None
                and record.snapshot_id != normalized_snapshot
            ):
                raise CoordinationError(
                    "acquisition snapshot does not match checkpointed authority"
                )
            if path:
                if not os.path.isfile(path):
                    raise LeaseServiceError(
                        "saved document path is missing or is not a regular file"
                    )
                if not isinstance(baseline, FileBaseline):
                    raise LeaseServiceError(
                        "saved document acquisition requires a file baseline"
                    )
                if not baseline_validated:
                    raise LeaseServiceError(
                        "saved document acquisition baseline was not validated"
                    )
                if normalized_snapshot is None:
                    raise LeaseServiceError(
                        "saved document acquisition requires a recovery snapshot"
                    )
                sha256 = str(baseline.sha256)
                if len(sha256) != 64 or any(
                    ch not in "0123456789abcdef" for ch in sha256
                ):
                    raise LeaseServiceError(
                        "saved document baseline has an invalid SHA-256"
                    )
                try:
                    info = os.stat(path)
                except OSError as exc:
                    raise LeaseServiceError(
                        f"saved document is unavailable: {exc}"
                    ) from exc
                current_identity = file_identity_for_path(
                    path, platform=self.identity_service.platform
                )
                failures = []
                if int(info.st_size) != baseline.size:
                    failures.append("size changed")
                if int(info.st_mtime_ns) != baseline.mtime_ns:
                    failures.append("modification time changed")
                if baseline.file_identity != current_identity:
                    failures.append("file identity changed")
                if record.document.file_identity != current_identity:
                    failures.append("registered document identity changed")
                if failures:
                    raise CoordinationError(
                        "saved document changed during acquisition: "
                        + "; ".join(failures)
                    )
            elif baseline is not None or baseline_validated:
                raise LeaseServiceError(
                    "unsaved document acquisition cannot have a file baseline"
                )
            idle = record.transitioned(
                LeaseState.LOCKED_IDLE,
                baseline=baseline,
                validation_complete=bool(path and baseline_validated),
                snapshot_id=normalized_snapshot,
            )
            try:
                idle = self._commit(record, idle)
            except CoordinationError:
                # Keep ACQUIRING in memory and on disk. The token is still
                # private, so only guarded recovery can resolve uncertainty.
                raise
            self._clear_acquiring_request(credential.document_session_uuid)
            return LeaseGrant(credential=credential, record=idle)

    def abort_acquisition(self, credential: LeaseCredential) -> dict[str, Any]:
        """CAS-remove an unreturned, mutation-free ACQUIRING reservation."""

        with self._lock:
            record = self._record_for_credential(
                credential, allowed_states={LeaseState.ACQUIRING}
            )
            path = self._sidecar_path(record)
            try:
                if path is not None:
                    self.sidecar_store.delete(path, expected=record)
            except SidecarError as exc:
                error_record = record.transitioned(
                    LeaseState.LOCKED_ERROR,
                    error=LeaseErrorInfo(
                        code="ACQUISITION_ROLLBACK_FAILED",
                        message=_bounded_text(str(exc), 2048),
                        at=self._utc_clock(),
                    ),
                )
                try:
                    self._commit(record, error_record)
                except CoordinationError:
                    self._records[credential.document_session_uuid] = error_record
                raise CoordinationError(
                    f"acquisition reservation could not be rolled back: {exc}"
                ) from exc
            self._records.pop(credential.document_session_uuid, None)
            self._last_sidecar_heartbeat_ns.pop(credential.document_session_uuid, None)
            self._closed_documents.pop(
                credential.document_session_uuid,
                None,
            )
            self._clear_acquiring_request(credential.document_session_uuid)
            return {
                "rolled_back": True,
                "document_session_uuid": credential.document_session_uuid,
                "generation": credential.generation,
            }

    def fail_acquisition_after_mutation(
        self,
        credential: LeaseCredential,
        *,
        request_id: str,
        message: str,
        dirty: bool = True,
        snapshot_id: str | None = None,
    ) -> LeaseRecord:
        """Retain acquisition authority after a live-state mutation.

        An acquisition credential has not yet been returned, so silently
        aborting after mutation would orphan changed state.  This exact typed
        event preserves the sidecar/registry fence for local recovery.
        """

        normalized_snapshot = None
        if snapshot_id:
            try:
                normalized_snapshot = str(uuid.UUID(str(snapshot_id)))
            except (TypeError, ValueError, AttributeError) as exc:
                raise LeaseServiceError(
                    "acquisition cancellation snapshot ID must be a UUID"
                ) from exc
        with self._lock:
            record = self._record_for_credential(
                credential,
                allowed_states={
                    LeaseState.ACQUIRING,
                    LeaseState.LOCKED_IDLE,
                    LeaseState.LOCKED_ERROR,
                },
            )
            error = LeaseErrorInfo(
                code="REQUEST_CANCELLED_AFTER_MUTATION",
                message=_bounded_text(message, 2048),
                at=self._utc_clock(),
                request_id=_bounded_text(request_id, 64) or None,
            )
            changes: dict[str, Any] = {
                "current_operation": "",
                "dirty": bool(dirty),
                "validation_complete": False,
                "error": error,
            }
            if normalized_snapshot is not None:
                changes["snapshot_id"] = normalized_snapshot
            if record.state == LeaseState.LOCKED_ERROR:
                updated = record.revised(**changes)
            else:
                updated = record.transitioned(LeaseState.LOCKED_ERROR, **changes)
            return self._commit(record, updated)

    def authorize(
        self,
        credential: LeaseCredential,
        *,
        selector: DocumentSelector | Mapping[str, Any] | str | None = None,
        allowed_states: Iterable[LeaseState] = _OWNER_AUTHORIZABLE_STATES,
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
                changes["current_operation"] = _bounded_diagnostic(
                    current_operation,
                    512,
                    secrets_to_remove=(credential.token,),
                )
            if task_summary is not None:
                changes["task_summary"] = _bounded_diagnostic(
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
                self._last_sidecar_heartbeat_ns[credential.document_session_uuid] = (
                    now_mono
                )
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
                changes["task_summary"] = _bounded_diagnostic(
                    task_summary,
                    1024,
                    secrets_to_remove=(credential.token,),
                )
            if current_operation is not None:
                changes["current_operation"] = _bounded_diagnostic(
                    current_operation,
                    512,
                    secrets_to_remove=(credential.token,),
                )
            updated = record.revised(**changes)
            return self._commit(record, updated).to_public_dict()

    def begin_mutation(
        self, credential: LeaseCredential, *, operation: str
    ) -> LeaseRecord:
        with self._lock:
            record = self._record_for_credential(
                credential, allowed_states={LeaseState.LOCKED_IDLE}
            )
            updated = record.transitioned(
                LeaseState.LOCKED_EDITING,
                current_operation=_bounded_text(operation, 512),
                last_mutation_revision=record.last_mutation_revision + 1,
                validation_complete=False,
                error=None,
            )
            return self._commit(record, updated)

    def begin_recovery(
        self, credential: LeaseCredential, *, operation: str
    ) -> LeaseRecord:
        """Begin an explicitly classified recovery from ``LOCKED_ERROR``."""

        with self._lock:
            record = self._record_for_credential(
                credential, allowed_states={LeaseState.LOCKED_ERROR}
            )
            updated = record.transitioned(
                LeaseState.LOCKED_EDITING,
                current_operation=_bounded_text(operation, 512),
                last_mutation_revision=record.last_mutation_revision + 1,
                validation_complete=False,
                error=None,
            )
            return self._commit(record, updated)

    def begin_recompute(self, credential: LeaseCredential) -> LeaseRecord:
        with self._lock:
            record = self._record_for_credential(
                credential,
                allowed_states={LeaseState.LOCKED_IDLE, LeaseState.LOCKED_EDITING},
            )
            mutation_revision = record.last_mutation_revision
            if record.state == LeaseState.LOCKED_IDLE:
                mutation_revision += 1
            updated = record.transitioned(
                LeaseState.LOCKED_RECOMPUTING,
                current_operation="Recomputing",
                last_mutation_revision=mutation_revision,
                validation_complete=False,
            )
            return self._commit(record, updated)

    def complete_operation(
        self, credential: LeaseCredential, *, dirty: bool
    ) -> LeaseRecord:
        with self._lock:
            record = self._record_for_credential(
                credential,
                allowed_states={
                    LeaseState.LOCKED_EDITING,
                    LeaseState.LOCKED_RECOMPUTING,
                },
            )
            updated = record.transitioned(
                LeaseState.LOCKED_IDLE,
                current_operation="",
                dirty=bool(dirty),
            )
            return self._commit(record, updated)

    def record_error(
        self,
        credential: LeaseCredential,
        *,
        code: str,
        message: str,
        request_id: str | None = None,
        dirty: bool | None = None,
    ) -> LeaseRecord:
        with self._lock:
            record = self._record_for_credential(credential)
            error = LeaseErrorInfo(
                code=_bounded_text(code, 128) or "UNKNOWN",
                message=_bounded_text(message, 2048),
                at=self._utc_clock(),
                request_id=_bounded_text(request_id, 64) or None,
            )
            changes: dict[str, Any] = {"error": error}
            if dirty is not None:
                changes["dirty"] = bool(dirty)
            if record.state == LeaseState.LOCKED_ERROR:
                updated = record.revised(**changes)
            else:
                updated = record.transitioned(LeaseState.LOCKED_ERROR, **changes)
            return self._commit(record, updated)

    def begin_save(self, credential: LeaseCredential) -> LeaseRecord:
        with self._lock:
            record = self._record_for_credential(
                credential,
                allowed_states={LeaseState.LOCKED_IDLE, LeaseState.LOCKED_ERROR},
            )
            updated = record.transitioned(
                LeaseState.LOCKED_SAVING,
                current_operation="Saving and verifying",
            )
            return self._commit(record, updated)

    def cancel_save_before_mutation(self, credential: LeaseCredential) -> LeaseRecord:
        """Return a preflight-only Save As conflict to idle without hiding writes."""

        with self._lock:
            record = self._record_for_credential(
                credential, allowed_states={LeaseState.LOCKED_SAVING}
            )
            pending = self._pending_save_as.get(credential.document_session_uuid)
            if pending is not None:
                path = self._sidecar_path(pending)
                if path is not None:
                    try:
                        self.sidecar_store.delete(path, expected=pending)
                    except SidecarError as exc:
                        raise CoordinationError(
                            f"unable to remove Save As reservation: {exc}"
                        ) from exc
                self._pending_save_as.pop(credential.document_session_uuid, None)
            updated = record.transitioned(
                LeaseState.LOCKED_IDLE,
                current_operation="",
                migration=None,
            )
            return self._commit(record, updated)

    def begin_cancellation(
        self,
        credential: LeaseCredential,
        *,
        request_id: str,
        operation: str = "Cancelling request",
        mutation_may_have_begun: bool = False,
    ) -> LeaseRecord:
        """Fence new writes while an authenticated request is being cancelled.

        This is a typed service event, not a caller-selected state transition.
        Repeating it for the same request is idempotent; a different request
        may not take over an in-progress cancellation.
        """

        request_id = _bounded_text(request_id, 64)
        if not request_id:
            raise LeaseServiceError("cancellation request_id is required")
        session_uuid = credential.document_session_uuid
        with self._lock:
            record = self._record_for_credential(
                credential,
                allowed_states={
                    LeaseState.LOCKED_IDLE,
                    LeaseState.LOCKED_EDITING,
                    LeaseState.LOCKED_RECOMPUTING,
                    LeaseState.LOCKED_SAVING,
                    LeaseState.LOCKED_ERROR,
                    LeaseState.CANCELLING,
                },
            )
            existing = self._cancellations.get(session_uuid)
            if record.state == LeaseState.CANCELLING:
                if existing is None or existing.request_id != request_id:
                    raise LeaseStateError(
                        "document is already cancelling a different request"
                    )
                if mutation_may_have_begun and not existing.mutation_may_have_begun:
                    self._cancellations[session_uuid] = replace(
                        existing, mutation_may_have_begun=True
                    )
                return record
            if record.state not in {
                LeaseState.LOCKED_IDLE,
                LeaseState.LOCKED_EDITING,
                LeaseState.LOCKED_RECOMPUTING,
                LeaseState.LOCKED_SAVING,
                LeaseState.LOCKED_ERROR,
            }:
                raise LeaseStateError(
                    f"request cancellation is forbidden in {record.state.value}"
                )
            context = _CancellationContext(
                request_id=request_id,
                previous_state=record.state,
                previous_operation=record.current_operation,
                mutation_may_have_begun=bool(mutation_may_have_begun),
            )
            updated = record.transitioned(
                LeaseState.CANCELLING,
                current_operation=_bounded_text(operation, 512),
            )
            committed = self._commit(record, updated)
            self._cancellations[session_uuid] = context
            return committed

    def complete_cancellation(
        self,
        credential: LeaseCredential,
        *,
        request_id: str,
        mutation_may_have_begun: bool,
        dirty: bool | None = None,
        message: str = "authenticated request cancelled",
    ) -> LeaseRecord:
        """Resolve ``CANCELLING`` after queued/running work is known complete.

        An exact pre-save destination reservation is CAS-removed only when no
        FreeCAD mutation/save invocation began.  Any uncertainty or possible
        mutation becomes ``LOCKED_ERROR`` and deliberately retains recovery
        sidecars.
        """

        request_id = _bounded_text(request_id, 64)
        session_uuid = credential.document_session_uuid
        with self._lock:
            record = self._record_for_credential(
                credential,
                allowed_states={
                    LeaseState.CANCELLING,
                    LeaseState.LOCKED_IDLE,
                    LeaseState.LOCKED_ERROR,
                },
            )
            context = self._cancellations.get(session_uuid)
            if context is None:
                # Repeated completion after the first result is harmless.
                if record.state in {LeaseState.LOCKED_IDLE, LeaseState.LOCKED_ERROR}:
                    return record
                raise LeaseStateError("document has no matching cancellation event")
            if context.request_id != request_id:
                raise LeaseStateError("cancellation completion request_id mismatch")
            if record.state != LeaseState.CANCELLING:
                raise LeaseStateError(
                    f"cancellation completion is forbidden in {record.state.value}"
                )
            may_have_mutated = bool(
                mutation_may_have_begun or context.mutation_may_have_begun
            )
            if may_have_mutated:
                error = LeaseErrorInfo(
                    code="REQUEST_CANCELLED_AFTER_MUTATION",
                    message=_bounded_text(message, 2048),
                    at=self._utc_clock(),
                    request_id=request_id,
                )
                updated = record.transitioned(
                    LeaseState.LOCKED_ERROR,
                    current_operation="",
                    dirty=True if dirty is None else bool(dirty),
                    validation_complete=False,
                    error=error,
                )
                committed = self._commit(record, updated)
                self._cancellations.pop(session_uuid, None)
                return committed

            pending = self._pending_save_as.get(session_uuid)
            if pending is not None:
                path = self._sidecar_path(pending)
                if path is not None:
                    try:
                        self.sidecar_store.delete(path, expected=pending)
                    except SidecarError as exc:
                        error = LeaseErrorInfo(
                            code="CANCELLATION_ROLLBACK_FAILED",
                            message=_bounded_text(str(exc), 2048),
                            at=self._utc_clock(),
                            request_id=request_id,
                        )
                        failed = record.transitioned(
                            LeaseState.LOCKED_ERROR,
                            dirty=bool(record.dirty),
                            validation_complete=False,
                            error=error,
                        )
                        self._commit(record, failed)
                        self._cancellations.pop(session_uuid, None)
                        raise CoordinationError(
                            f"unable to remove Save As reservation: {exc}"
                        ) from exc
                self._pending_save_as.pop(session_uuid, None)

            target = (
                LeaseState.LOCKED_ERROR
                if context.previous_state == LeaseState.LOCKED_ERROR
                else LeaseState.LOCKED_IDLE
            )
            updated = record.transitioned(
                target,
                current_operation=(
                    context.previous_operation
                    if target == LeaseState.LOCKED_ERROR
                    else ""
                ),
                migration=None,
            )
            committed = self._commit(record, updated)
            self._cancellations.pop(session_uuid, None)
            return committed

    def reserve_save_as(
        self, credential: LeaseCredential, destination: str | os.PathLike[str]
    ) -> LeaseRecord:
        """Publish a destination recovery record before FreeCAD calls saveAs()."""

        with self._lock:
            record = self._record_for_credential(
                credential, allowed_states={LeaseState.LOCKED_SAVING}
            )
            session_uuid = credential.document_session_uuid
            if session_uuid in self._pending_save_as:
                raise LeaseConflictError("a Save As reservation already exists")
            destination_identity = self.identity_service.preview_path_update(
                session_uuid, destination
            )
            migration_id = str(uuid.uuid4())
            source_migration = SaveAsMigration(
                migration_id=migration_id,
                source_canonical_path=record.document.canonical_path,
                source_comparison_key=record.document.comparison_key,
                destination_canonical_path=destination_identity.canonical_path or "",
                destination_comparison_key=destination_identity.comparison_key or "",
                role=SaveAsMigrationRole.SOURCE,
            )
            destination_migration = replace(
                source_migration,
                role=SaveAsMigrationRole.DESTINATION,
            )
            pending = replace(
                record,
                document=destination_identity,
                state=LeaseState.ACQUIRING,
                record_revision=1,
                state_revision=1,
                current_operation="Save As destination reserved",
                baseline=None,
                validation_complete=False,
                migration=destination_migration,
            )
            path = self._sidecar_path(pending)
            if path is None:
                raise LeaseServiceError("Save As destination has no sidecar path")
            try:
                self.sidecar_store.create(path, pending)
            except SidecarError as exc:
                raise LeaseConflictError(
                    f"Save As destination is locked or unavailable: {exc}"
                ) from exc
            self._pending_save_as[session_uuid] = pending
            source_linked = record.revised(migration=source_migration)
            try:
                self._commit(record, source_linked)
            except CoordinationError:
                # The destination reservation remains authoritative and
                # self-describes its source.  The caller may explicitly cancel
                # before saveAs; a crash leaves both paths safely fenced.
                raise
            return pending

    def commit_save_as(
        self,
        credential: LeaseCredential,
        *,
        destination: str | os.PathLike[str],
        baseline: FileBaseline,
        snapshot_id: str | None = None,
    ) -> LeaseRecord:
        """Promote destination first, then CAS-remove the source sidecar last."""

        with self._lock:
            current = self._record_for_credential(
                credential, allowed_states={LeaseState.LOCKED_SAVING}
            )
            session_uuid = credential.document_session_uuid
            pending = self._pending_save_as.get(session_uuid)
            if pending is None:
                raise CoordinationError("Save As destination was not reserved")
            canonical, comparison = canonicalize_path(
                destination, platform=self.identity_service.platform
            )
            if pending.document.comparison_key != comparison:
                raise CoordinationError("Save As destination reservation changed")
            source_migration = current.migration
            destination_migration = pending.migration
            if (
                source_migration is None
                or destination_migration is None
                or source_migration.role != SaveAsMigrationRole.SOURCE
                or destination_migration.role != SaveAsMigrationRole.DESTINATION
                or source_migration.migration_id != destination_migration.migration_id
                or replace(
                    source_migration,
                    role=SaveAsMigrationRole.DESTINATION,
                )
                != destination_migration
            ):
                raise CoordinationError("Save As recovery linkage changed")
            # Build the promoted record without changing identity aliases.  A
            # destination-sidecar failure must leave selector resolution on
            # the still-authoritative source document.
            updated_identity = self.identity_service.preview_path_update(
                session_uuid, canonical
            )
            promoted = replace(
                pending,
                document=updated_identity,
                state=LeaseState.LOCKED_IDLE,
                record_revision=pending.record_revision + 1,
                state_revision=pending.state_revision + 1,
                current_operation="",
                dirty=False,
                error=None,
                baseline=baseline,
                last_successful_save_at=self._utc_clock(),
                last_verified_save_revision=current.last_mutation_revision,
                last_mutation_revision=current.last_mutation_revision,
                validation_complete=True,
                snapshot_id=_bounded_text(snapshot_id, 512) or current.snapshot_id,
            )
            destination_path = self._sidecar_path(pending)
            assert destination_path is not None
            try:
                self.sidecar_store.replace(destination_path, promoted, expected=pending)
            except SidecarError as exc:
                raise CoordinationError(
                    f"unable to promote Save As destination lease: {exc}"
                ) from exc

            try:
                published_identity = self.identity_service.update_path(
                    session_uuid, canonical
                )
                if published_identity != updated_identity:
                    raise CoordinationError(
                        "Save As destination identity changed during promotion"
                    )
            except Exception as exc:
                error_record = promoted.transitioned(
                    LeaseState.LOCKED_ERROR,
                    error=LeaseErrorInfo(
                        code="SAVE_AS_IDENTITY_REBIND_FAILED",
                        message=_bounded_text(str(exc), 2048),
                        at=self._utc_clock(),
                    ),
                )
                try:
                    self.sidecar_store.replace(
                        destination_path, error_record, expected=promoted
                    )
                finally:
                    self._records[session_uuid] = error_record
                    self._pending_save_as.pop(session_uuid, None)
                if isinstance(exc, CoordinationError):
                    raise
                raise CoordinationError(
                    f"unable to publish Save As document identity: {exc}"
                ) from exc

            source_path = self._sidecar_path(current)
            try:
                if source_path is not None and source_path != destination_path:
                    self.sidecar_store.delete(source_path, expected=current)
            except SidecarError as exc:
                error_record = promoted.transitioned(
                    LeaseState.LOCKED_ERROR,
                    error=LeaseErrorInfo(
                        code="SAVE_AS_SOURCE_RELEASE_FAILED",
                        message=_bounded_text(str(exc), 2048),
                        at=self._utc_clock(),
                    ),
                )
                try:
                    self.sidecar_store.replace(
                        destination_path, error_record, expected=promoted
                    )
                finally:
                    self._records[session_uuid] = error_record
                    self._pending_save_as.pop(session_uuid, None)
                raise CoordinationError(
                    f"Save As retained its source recovery lock: {exc}"
                ) from exc

            finalized = promoted.revised(migration=None)
            try:
                self.sidecar_store.replace(
                    destination_path,
                    finalized,
                    expected=promoted,
                )
            except SidecarError as exc:
                error_record = promoted.transitioned(
                    LeaseState.LOCKED_ERROR,
                    error=LeaseErrorInfo(
                        code="SAVE_AS_LINKAGE_FINALIZE_FAILED",
                        message=_bounded_text(str(exc), 2048),
                        at=self._utc_clock(),
                    ),
                )
                try:
                    self.sidecar_store.replace(
                        destination_path,
                        error_record,
                        expected=promoted,
                    )
                except SidecarError:
                    # The first replacement may have completed durably before
                    # reporting an error.  Retain the stricter in-memory state;
                    # registry/sidecar disagreement blocks further writes.
                    pass
                finally:
                    self._records[session_uuid] = error_record
                    self._pending_save_as.pop(session_uuid, None)
                raise CoordinationError(
                    f"Save As recovery linkage could not be finalized: {exc}"
                ) from exc
            self._records[session_uuid] = finalized
            self._pending_save_as.pop(session_uuid, None)
            self._last_sidecar_heartbeat_ns[session_uuid] = self._monotonic_ns()
            return finalized

    def mark_save_verified(
        self,
        credential: LeaseCredential,
        *,
        baseline: FileBaseline | None = None,
        snapshot_id: str | None = None,
    ) -> LeaseRecord:
        with self._lock:
            record = self._record_for_credential(
                credential, allowed_states={LeaseState.LOCKED_SAVING}
            )
            if baseline is None:
                path = record.document.canonical_path
                if not path:
                    raise CleanReleaseError(
                        "an unsaved document cannot be verified without a saved path"
                    )
                baseline = capture_file_baseline(
                    path, platform=self.identity_service.platform
                )
            refreshed_document = record.document
            if record.document.canonical_path:
                # FreeCAD may implement save via temporary-file replacement,
                # changing the filesystem identity while preserving the path.
                refreshed_document = self.identity_service.update_path(
                    record.document.session_uuid, record.document.canonical_path
                )
            updated = record.transitioned(
                LeaseState.LOCKED_IDLE,
                document=refreshed_document,
                current_operation="",
                dirty=False,
                error=None,
                baseline=baseline,
                last_successful_save_at=self._utc_clock(),
                last_verified_save_revision=record.last_mutation_revision,
                validation_complete=True,
                snapshot_id=_bounded_text(snapshot_id, 512) or record.snapshot_id,
            )
            return self._commit(record, updated)

    def import_adjacent_foreign_recovery(
        self,
        selector: DocumentSelector | Mapping[str, Any] | str,
        *,
        live_document: DocumentIdentity,
    ) -> dict[str, Any]:
        """Import one strict v2 sidecar without changing its persisted authority.

        The returned/public record is redacted. Malformed, unknown-schema,
        missing, and mismatched-path records are never added to the foreign
        registry and are never rewritten or removed. A replaced filesystem
        identity is accepted only for an explicit ``UNLOCKED_DIRTY`` local
        acknowledgement; acquisition must still prove its owner dead and
        independently validate the newly saved file before CAS fencing it.
        """

        registered = self.identity_service.resolve(selector)
        if not isinstance(live_document, DocumentIdentity):
            raise ForeignRecoveryError(
                "fresh live DocumentIdentity evidence is required"
            )
        if live_document != registered:
            raise ForeignRecoveryError(
                "live document evidence does not match the registered open document"
            )
        if not registered.canonical_path:
            raise ForeignRecoveryError(
                "an unsaved document cannot have an adjacent recovery sidecar"
            )
        path = sidecar_path_for(registered.canonical_path)
        with self._lock:
            if registered.session_uuid in self._records:
                raise LeaseConflictError(
                    "the open document already has a local lease record"
                )
            try:
                persisted = self.sidecar_store.read(path)
            except SidecarError as exc:
                raise ForeignRecoveryError(
                    f"adjacent sidecar is unavailable or invalid: {exc}"
                ) from exc
            self._assert_foreign_document_exact(
                registered,
                persisted,
                allow_unreturned_file_replacement=True,
                allow_saved_dirty_file_replacement=True,
            )
            existing = self._foreign_records.get(registered.session_uuid)
            if existing is not None:
                if (
                    existing.local_document != registered
                    or existing.persisted != persisted
                ):
                    raise CoordinationError(
                        "the imported foreign recovery authority changed"
                    )
                return existing.to_public_dict()
            imported = ForeignRecoveryRecord(
                local_document=registered,
                persisted=persisted,
                imported_at=self._utc_clock(),
            )
            self._foreign_records[registered.session_uuid] = imported
            self._generations[registered.session_uuid] = max(
                self._generations.get(registered.session_uuid, 0),
                persisted.generation,
            )
            return imported.to_public_dict()

    def confirmed_takeover_foreign_recovery(
        self,
        selector: DocumentSelector | Mapping[str, Any] | str,
        *,
        live_document: DocumentIdentity,
        confirmed: bool,
        document_dirty: bool,
        reason: str,
    ) -> LeaseRecord:
        """Fence a proven-dead same-host owner and bind the local document UUID."""

        if confirmed is not True:
            raise ForeignRecoveryError(
                "foreign recovery takeover requires explicit local confirmation"
            )
        clean_reason = _bounded_text(reason, 2048)
        if not clean_reason:
            raise ForeignRecoveryError("foreign recovery takeover requires a reason")
        registered = self.identity_service.resolve(selector)
        if not isinstance(live_document, DocumentIdentity):
            raise ForeignRecoveryError(
                "fresh live DocumentIdentity evidence is required"
            )
        if live_document != registered:
            raise ForeignRecoveryError(
                "live document evidence does not match the registered open document"
            )

        with self._lock:
            if registered.session_uuid in self._records:
                raise LeaseConflictError(
                    "the open document already has a local lease record"
                )
            foreign = self._foreign_records.get(registered.session_uuid)
            if foreign is None:
                raise LeaseConflictError(
                    "the open document has no imported foreign recovery record"
                )
            if foreign.local_document != registered:
                raise ForeignRecoveryError(
                    "the open document identity changed after foreign import"
                )
            if not registered.canonical_path:
                raise ForeignRecoveryError(
                    "foreign recovery takeover requires a saved open document"
                )
            path = sidecar_path_for(registered.canonical_path)
            try:
                persisted = self.sidecar_store.read(path)
            except SidecarError as exc:
                raise CoordinationError(
                    f"foreign recovery sidecar is unavailable or invalid: {exc}"
                ) from exc
            if persisted != foreign.persisted:
                raise CoordinationError(
                    "foreign recovery authority changed after import"
                )
            self._assert_foreign_document_exact(registered, persisted)
            death_proof = self._prove_foreign_owner_dead(persisted.owner)

            eligible = {
                LeaseState.ACQUIRING,
                LeaseState.LOCKED_IDLE,
                LeaseState.LOCKED_EDITING,
                LeaseState.LOCKED_RECOMPUTING,
                LeaseState.LOCKED_SAVING,
                LeaseState.LOCKED_ERROR,
                LeaseState.CANCELLING,
                LeaseState.RELEASING,
                LeaseState.STALE,
            }
            if persisted.state not in eligible:
                raise ForeignRecoveryError(
                    f"state {persisted.state.value} requires a different local recovery"
                )

            current = persisted
            if current.state in {LeaseState.ACQUIRING, LeaseState.RELEASING}:
                uncertain = current.transitioned(
                    LeaseState.LOCKED_ERROR,
                    error=LeaseErrorInfo(
                        code="FOREIGN_TAKEOVER_DURING_TRANSITION",
                        message=clean_reason,
                        at=self._utc_clock(),
                    ),
                )
                try:
                    self.sidecar_store.replace(path, uncertain, expected=current)
                except SidecarError as exc:
                    raise CoordinationError(
                        f"foreign transition could not be fenced: {exc}"
                    ) from exc
                current = uncertain
                foreign = replace(foreign, persisted=current)
                self._foreign_records[registered.session_uuid] = foreign

            raw_replacement = self._token_factory()
            if not raw_replacement:
                raise ForeignRecoveryError(
                    "token factory returned an empty fencing secret"
                )
            replacement_fingerprint = token_fingerprint(raw_replacement)
            if secrets.compare_digest(
                replacement_fingerprint, current.token_fingerprint
            ):
                raise ForeignRecoveryError(
                    "token factory did not rotate the fencing digest"
                )
            generation = (
                max(
                    current.generation,
                    self._generations.get(registered.session_uuid, 0),
                )
                + 1
            )
            taken = current.transitioned(
                LeaseState.USER_INTERVENED,
                document=registered,
                generation=generation,
                token_fingerprint=replacement_fingerprint,
                current_operation="",
                user_intervened=True,
                dirty=bool(document_dirty),
                error=LeaseErrorInfo(
                    code="USER_INTERVENED",
                    message=_bounded_text(f"{clean_reason} ({death_proof})", 2048),
                    at=self._utc_clock(),
                ),
            )
            try:
                self.sidecar_store.replace(path, taken, expected=current)
            except SidecarError as exc:
                raise CoordinationError(f"foreign takeover CAS failed: {exc}") from exc
            self._records[registered.session_uuid] = taken
            self._foreign_records.pop(registered.session_uuid, None)
            self._generations[registered.session_uuid] = generation
            self._last_sidecar_heartbeat_ns.pop(registered.session_uuid, None)
            return taken

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
                        message=_bounded_text(reason, 2048),
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
                    message=_bounded_text(reason, 2048),
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
                validation_complete=(
                    record.validation_complete if not dirty else False
                ),
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
            if record.state not in _RECOVERY_IDENTITY_REFRESHABLE_STATES:
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

    def handle_document_closed(
        self,
        selector: DocumentSelector | Mapping[str, Any] | str,
        *,
        document: Any,
    ) -> LeaseRecord | dict[str, Any] | None:
        """Retain recovery authority or unregister an unlocked closed proxy."""

        identity = self.identity_service.resolve(selector)
        with self._lock:
            exact = self.identity_service.inspect_registered_document(
                identity.session_uuid,
                document,
            )
            record = self._records.get(identity.session_uuid)
            if record is not None:
                if record.state not in {
                    LeaseState.USER_INTERVENED,
                    LeaseState.UNLOCKED_DIRTY,
                }:
                    raise LeaseStateError(
                        "document close can be marked only after local fencing",
                        details={"state": record.state.value},
                    )
                self._assert_sidecar_matches(record)
                if exact != record.document:
                    raise CoordinationError(
                        "closed live proxy does not match lease authority"
                    )
                self._closed_documents[identity.session_uuid] = (
                    id(document),
                    exact,
                )
                return record

            foreign = self._foreign_records.get(identity.session_uuid)
            if foreign is not None:
                if exact != foreign.local_document:
                    raise CoordinationError(
                        "closed live proxy does not match foreign recovery authority"
                    )
                if not exact.canonical_path:
                    raise ForeignRecoveryError(
                        "foreign recovery document has no saved path"
                    )
                try:
                    persisted = self.sidecar_store.read(
                        sidecar_path_for(exact.canonical_path)
                    )
                except SidecarError as exc:
                    raise CoordinationError(
                        f"foreign recovery sidecar is unavailable or invalid: {exc}"
                    ) from exc
                if persisted != foreign.persisted:
                    raise CoordinationError(
                        "foreign recovery authority changed before document close"
                    )
                self._closed_documents[identity.session_uuid] = (
                    id(document),
                    exact,
                )
                return foreign.to_public_dict()

            if identity.session_uuid in self._pending_save_as:
                raise CoordinationError(
                    "a pending Save As authority cannot be unregistered"
                )
            self._closed_documents.pop(identity.session_uuid, None)
            self.identity_service.unregister(identity.session_uuid)
            return None

    def rebind_closed_recovery_document(
        self,
        *,
        document: Any,
    ) -> DocumentIdentity:
        """Rebind a same-file proxy after an observed recovery-document reopen."""

        name = str(getattr(document, "Name", "") or "").strip()
        raw_path = str(getattr(document, "FileName", "") or "").strip()
        if not name or not raw_path:
            raise LocalRecoveryError(
                "closed-document recovery requires a saved named document"
            )
        canonical, comparison = canonicalize_path(
            raw_path,
            platform=self.identity_service.platform,
        )
        observed_file = file_identity_for_path(
            canonical,
            platform=self.identity_service.platform,
        )
        identity = self.identity_service.resolve(
            {
                "document_name": name,
                "canonical_path": canonical,
            }
        )
        with self._lock:
            closed = self._closed_documents.get(identity.session_uuid)
            if closed is None:
                raise LocalRecoveryError(
                    "the previous live document was not observed closing"
                )
            previous_proxy_id, closed_identity = closed
            if id(document) == previous_proxy_id:
                raise LocalRecoveryError(
                    "closed-document recovery requires a replacement proxy"
                )
            record = self._records.get(identity.session_uuid)
            foreign = self._foreign_records.get(identity.session_uuid)
            if record is not None:
                if record.state not in {
                    LeaseState.USER_INTERVENED,
                    LeaseState.UNLOCKED_DIRTY,
                }:
                    raise LeaseStateError(
                        "closed-document rebind requires local recovery authority",
                        details={"state": record.state.value},
                    )
                self._assert_sidecar_matches(record)
                authoritative = record.document
            elif foreign is not None:
                if not identity.canonical_path:
                    raise ForeignRecoveryError(
                        "foreign recovery document has no saved path"
                    )
                try:
                    persisted = self.sidecar_store.read(
                        sidecar_path_for(identity.canonical_path)
                    )
                except SidecarError as exc:
                    raise CoordinationError(
                        f"foreign recovery sidecar is unavailable or invalid: {exc}"
                    ) from exc
                if persisted != foreign.persisted:
                    raise CoordinationError(
                        "foreign recovery authority changed after document close"
                    )
                authoritative = foreign.local_document
            else:
                raise LeaseConflictError(
                    "the closed document has no retained recovery authority"
                )
            if (
                closed_identity != authoritative
                or name != authoritative.name
                or comparison != authoritative.comparison_key
                or observed_file != authoritative.file_identity
            ):
                raise CoordinationError(
                    "reopened document does not match the closed file identity"
                )
            rebound = self.identity_service.rebind_document(
                identity.session_uuid,
                document,
            )
            if rebound != authoritative:
                raise CoordinationError(
                    "reopened document rebind changed lease identity"
                )
            self._closed_documents.pop(identity.session_uuid, None)
            return rebound

    def acknowledge_local_dirty(
        self,
        selector: DocumentSelector | Mapping[str, Any] | str,
        *,
        document_dirty: bool,
        reason: str = "Local user chose to keep the document dirty",
    ) -> LeaseRecord:
        """Persist ``UNLOCKED_DIRTY`` after an explicit local confirmation."""

        if document_dirty is not True:
            raise LocalRecoveryError(
                "keep-dirty acknowledgement requires a currently dirty document"
            )
        identity = self.identity_service.resolve(selector)
        with self._lock:
            record = self._records.get(identity.session_uuid)
            if record is None:
                raise LeaseConflictError("the selected document has no recovery record")
            if record.state == LeaseState.UNLOCKED_DIRTY:
                return record
            if record.state != LeaseState.USER_INTERVENED:
                raise LeaseStateError(
                    "keep-dirty acknowledgement requires a prior local takeover",
                    details={"state": record.state.value},
                )
            if identity.session_uuid in self._pending_save_as:
                raise LocalRecoveryError(
                    "a pending Save As destination requires guarded recovery"
                )
            self._assert_sidecar_matches(record)
            updated = record.transitioned(
                LeaseState.UNLOCKED_DIRTY,
                current_operation="",
                dirty=True,
                user_intervened=True,
                validation_complete=False,
                error=LeaseErrorInfo(
                    code="DIRTY_ACKNOWLEDGED",
                    message=_bounded_text(reason, 2048),
                    at=self._utc_clock(),
                ),
            )
            return self._commit(record, updated)

    def complete_local_save_and_clear(
        self,
        selector: DocumentSelector | Mapping[str, Any] | str,
        *,
        verified_baseline: FileBaseline,
        baseline_validated: bool,
        document_modified: bool,
    ) -> dict[str, Any]:
        """CAS-clear a locally recovered lease after an independently verified save.

        The GUI must first use ``SaveService`` with archive, matching-worker,
        and domain validation. This method performs only the final lightweight
        stat/file-identity and GUI-document modified-state checks before publishing
        ``RELEASING`` and compare-and-removing the sidecar. No full hash runs
        under the service lock or on Qt, and no lease token is accepted.
        """

        if not isinstance(verified_baseline, FileBaseline):
            raise LocalRecoveryError("a verified file baseline is required")
        if baseline_validated is not True:
            raise LocalRecoveryError(
                "independent archive/domain baseline validation is required"
            )
        if document_modified:
            raise LocalRecoveryError("FreeCAD still reports the document as dirty")
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
                    "local save-and-clear requires takeover or dirty acknowledgement",
                    details={"state": record.state.value},
                )
            if identity.session_uuid in self._pending_save_as:
                raise LocalRecoveryError(
                    "a pending Save As destination requires guarded recovery"
                )
            self._assert_sidecar_matches(record)
            path = record.document.canonical_path
            if not path:
                raise LocalRecoveryError(
                    "an unsaved document requires guarded Save As recovery"
                )
            try:
                info = os.stat(path)
                current_identity = file_identity_for_path(
                    path, platform=self.identity_service.platform
                )
            except (DocumentIdentityError, OSError) as exc:
                raise LocalRecoveryError(
                    f"unable to revalidate the saved document: {exc}"
                ) from exc
            if (
                int(info.st_size) != verified_baseline.size
                or int(info.st_mtime_ns) != verified_baseline.mtime_ns
                or current_identity != verified_baseline.file_identity
            ):
                raise LocalRecoveryError("the saved file changed after verification")
            try:
                refreshed_document = self.identity_service.update_path(
                    identity.session_uuid, path
                )
            except Exception as exc:
                raise LocalRecoveryError(
                    f"unable to refresh saved document identity: {exc}"
                ) from exc
            if (
                verified_baseline.file_identity is not None
                and refreshed_document.file_identity != verified_baseline.file_identity
            ):
                raise LocalRecoveryError(
                    "saved document identity does not match its verified baseline"
                )

            releasing = record.transitioned(
                LeaseState.RELEASING,
                document=refreshed_document,
                current_operation="Local save verified; clearing lease",
                dirty=False,
                error=None,
                baseline=verified_baseline,
                last_successful_save_at=self._utc_clock(),
                last_verified_save_revision=record.last_mutation_revision,
                validation_complete=True,
            )
            self._commit(record, releasing)
            sidecar_path = self._sidecar_path(releasing)
            try:
                if sidecar_path is not None:
                    self.sidecar_store.delete(sidecar_path, expected=releasing)
            except SidecarError as exc:
                failed = releasing.transitioned(
                    LeaseState.LOCKED_ERROR,
                    error=LeaseErrorInfo(
                        code="LOCAL_SIDECAR_RELEASE_FAILED",
                        message=_bounded_text(str(exc), 2048),
                        at=self._utc_clock(),
                    ),
                )
                try:
                    self._commit(releasing, failed)
                except CoordinationError:
                    self._records[identity.session_uuid] = failed
                raise CoordinationError(
                    f"local save succeeded but sidecar removal failed: {exc}"
                ) from exc

            terminal = releasing.transitioned(
                LeaseState.UNLOCKED_SAVED, current_operation=""
            )
            result = terminal.to_public_dict()
            self._records.pop(identity.session_uuid, None)
            self._last_sidecar_heartbeat_ns.pop(identity.session_uuid, None)
            self._closed_documents.pop(identity.session_uuid, None)
            return result

    def mark_stale(
        self,
        selector: DocumentSelector | Mapping[str, Any] | str,
        *,
        reason: str = "Lease heartbeat expired",
    ) -> LeaseRecord:
        identity = self.identity_service.resolve(selector)
        with self._lock:
            record = self._records.get(identity.session_uuid)
            if record is None:
                raise LeaseConflictError("the selected document has no active lease")
            self._assert_sidecar_matches(record)
            if record.state == LeaseState.STALE:
                return record
            updated = record.transitioned(
                LeaseState.STALE,
                error=LeaseErrorInfo(
                    code="LEASE_STALE",
                    message=_bounded_text(reason, 2048),
                    at=self._utc_clock(),
                ),
            )
            return self._commit(record, updated)

    def mark_expired_stale(self, *, now_monotonic_ns: int | None = None) -> list[str]:
        """Persist stale state for expired leases without deleting anything."""

        now = self._monotonic_ns() if now_monotonic_ns is None else now_monotonic_ns
        changed: list[str] = []
        with self._lock:
            for session_uuid, record in list(self._records.items()):
                if record.state in {
                    LeaseState.STALE,
                    LeaseState.USER_INTERVENED,
                    LeaseState.UNLOCKED_SAVED,
                    LeaseState.UNLOCKED_DIRTY,
                }:
                    continue
                owner_exit_proof = ""
                if (
                    record.state == LeaseState.LOCKED_IDLE
                    and self._is_recoverable_local_mcp_orphan_candidate(record)
                ):
                    with contextlib.suppress(LocalRecoveryError):
                        owner_exit_proof = self._prove_local_mcp_owner_dead(
                            record.owner
                        )
                heartbeat_expired = (
                    now - record.monotonic_heartbeat_ns > self._stale_after_ns
                )
                if not owner_exit_proof and not heartbeat_expired:
                    continue
                error_code = (
                    "LEASE_OWNER_EXITED" if owner_exit_proof else "LEASE_STALE"
                )
                error_message = (
                    "Credential-owning MCP process exited: " + owner_exit_proof
                    if owner_exit_proof
                    else "Lease heartbeat expired"
                )
                updated = record.transitioned(
                    LeaseState.STALE,
                    error=LeaseErrorInfo(
                        code=error_code,
                        message=error_message,
                        at=self._utc_clock(),
                    ),
                )
                self._commit(record, updated)
                changed.append(session_uuid)
        return changed

    def reconcile_stale(
        self,
        credential: LeaseCredential,
        *,
        validation: LiveDocumentValidation,
    ) -> LeaseRecord:
        """Resume only when fresh live-document and baseline evidence is exact."""

        with self._lock:
            record = self._record_for_credential(
                credential, allowed_states={LeaseState.STALE}
            )
            try:
                self._validate_live_evidence(record, validation)
                if bool(validation.document_modified) != bool(record.dirty):
                    raise LiveDocumentValidationError(
                        "live GUI document modified state no longer matches the stale record",
                        details={
                            "expected_modified": bool(record.dirty),
                            "actual_modified": bool(validation.document_modified),
                        },
                    )
            except LiveDocumentValidationError as exc:
                failed = record.revised(
                    error=LeaseErrorInfo(
                        code=exc.code,
                        message=_bounded_text(str(exc), 2048),
                        at=self._utc_clock(),
                    )
                )
                self._commit(record, failed)
                raise
            updated = record.transitioned(
                LeaseState.LOCKED_IDLE,
                error=None,
                last_heartbeat_at=self._utc_clock(),
                monotonic_heartbeat_ns=self._monotonic_ns(),
            )
            return self._commit(record, updated)

    def release_clean(
        self,
        credential: LeaseCredential,
        *,
        validation: LiveDocumentValidation,
    ) -> dict[str, Any]:
        """CAS-remove a lease only after a clean, current, validated save."""

        with self._lock:
            record = self._record_for_credential(
                credential, allowed_states={LeaseState.LOCKED_IDLE}
            )
            try:
                self._validate_live_evidence(record, validation)
                if validation.document_modified:
                    raise LiveDocumentValidationError(
                        "FreeCAD reports that the live document is dirty"
                    )
            except LiveDocumentValidationError as exc:
                failed = record.transitioned(
                    LeaseState.LOCKED_ERROR,
                    error=LeaseErrorInfo(
                        code=exc.code,
                        message=_bounded_text(str(exc), 2048),
                        at=self._utc_clock(),
                    ),
                    dirty=bool(
                        record.dirty or getattr(validation, "document_modified", False)
                    ),
                )
                self._commit(record, failed)
                raise
            failures: list[str] = []
            if record.dirty:
                failures.append("document is dirty")
            if not record.validation_complete:
                failures.append("validation is incomplete")
            if record.error is not None:
                failures.append("an unresolved lease error exists")
            if record.baseline is None:
                failures.append("no verified file baseline exists")
            if record.document.canonical_path is None:
                failures.append("document has no saved path")
            if record.last_verified_save_revision < record.last_mutation_revision:
                failures.append("verified save predates the last mutation")
            if failures:
                raise CleanReleaseError(
                    "; ".join(failures), details={"failures": failures}
                )
            releasing = record.transitioned(
                LeaseState.RELEASING, current_operation="Finalizing lease"
            )
            self._commit(record, releasing)
            path = self._sidecar_path(releasing)
            try:
                if path is not None:
                    self.sidecar_store.delete(path, expected=releasing)
            except SidecarError as exc:
                error_record = releasing.transitioned(
                    LeaseState.LOCKED_ERROR,
                    error=LeaseErrorInfo(
                        code="SIDECAR_RELEASE_FAILED",
                        message=_bounded_text(str(exc), 2048),
                        at=self._utc_clock(),
                    ),
                )
                try:
                    self._commit(releasing, error_record)
                except CoordinationError:
                    # Keep the stricter in-memory state; future authorization
                    # will still fail because registry and disk disagree.
                    self._records[credential.document_session_uuid] = error_record
                raise CoordinationError(
                    f"clean release could not remove sidecar: {exc}"
                ) from exc
            terminal = releasing.transitioned(
                LeaseState.UNLOCKED_SAVED, current_operation=""
            )
            result = terminal.to_public_dict()
            self._records.pop(credential.document_session_uuid, None)
            self._last_sidecar_heartbeat_ns.pop(credential.document_session_uuid, None)
            self._closed_documents.pop(
                credential.document_session_uuid,
                None,
            )
            return result

    def get(
        self, selector: DocumentSelector | Mapping[str, Any] | str
    ) -> dict[str, Any] | None:
        identity = self.identity_service.resolve(selector)
        with self._lock:
            record = self._records.get(identity.session_uuid)
            return record.to_public_dict() if record else None

    def list_records(self) -> list[dict[str, Any]]:
        with self._lock:
            return [record.to_public_dict() for record in self._records.values()]

    def has_unresolved_owner(self, mcp_runtime_id: str) -> bool:
        """Return whether an MCP runtime still owns local lease authority.

        The request-id journal uses this conservative process-local predicate
        to retain mutation tombstones for the complete lease/recovery
        lifetime.  Every registry state counts, including acquiring, stale,
        error, user-intervened, and dirty-recovery records; only an exact
        service resolution removes the owner from consideration.
        """

        runtime_id = str(mcp_runtime_id or "")
        if not runtime_id:
            return False
        with self._lock:
            return any(
                record.owner.mcp_instance_id == runtime_id
                for record in self._records.values()
            )

    def get_foreign_recovery(
        self, selector: DocumentSelector | Mapping[str, Any] | str
    ) -> dict[str, Any] | None:
        identity = self.identity_service.resolve(selector)
        with self._lock:
            foreign = self._foreign_records.get(identity.session_uuid)
            return foreign.to_public_dict() if foreign else None

    def refresh_orphaned_foreign_document_identity(
        self, *, document: Any
    ) -> DocumentIdentity:
        """Repair exact-proxy identity drift for a recoverable missing sidecar.

        Registration can detect an identity mismatch before acquisition gets a
        chance to run its full hash. This bounded repair locates only the exact
        previously registered proxy, proves its foreign authority inactive,
        and accepts a refresh only when the on-disk metadata still matches its
        saved baseline. The acquisition path repeats the check with SHA-256
        evidence before publishing new authority. A legacy worker-snapshot
        false-positive remains dirty when the live proxy says it is dirty.
        """

        session_uuid = self.identity_service.registered_session_uuid(document)
        with self._lock:
            foreign = self._foreign_records.get(session_uuid)
            if foreign is None:
                raise LeaseConflictError(
                    "the registered document has no foreign recovery record"
                )
            previous = foreign.persisted
            if not self._is_missing_sidecar_foreign_recovery_candidate(previous):
                raise ForeignRecoveryError(
                    "foreign authority lacks a verified recoverable saved baseline"
                )
            canonical_path = foreign.local_document.canonical_path
            if not canonical_path:
                raise ForeignRecoveryError(
                    "orphan identity repair requires a saved document"
                )
            path = sidecar_path_for(canonical_path)
            if os.path.lexists(path):
                raise CoordinationError(
                    "foreign sidecar still exists; identity repair is not automatic"
                )
            self._prove_orphaned_foreign_authority_inactive(foreign)
            observed = self.identity_service.inspect_registered_document(
                session_uuid, document
            )
            if (
                observed.name != foreign.local_document.name
                or observed.comparison_key != foreign.local_document.comparison_key
                or observed.comparison_key != previous.document.comparison_key
            ):
                raise ForeignRecoveryError(
                    "live document name or path changed after foreign import"
                )
            baseline = previous.baseline
            if not isinstance(baseline, FileBaseline):
                raise ForeignRecoveryError(
                    "foreign clean authority has no valid saved-file baseline"
                )
            self._assert_current_baseline(
                observed,
                baseline,
                error_type=ForeignRecoveryError,
            )
            refreshed = self.identity_service.refresh_saved_document(document)
            if (
                refreshed.session_uuid != session_uuid
                or refreshed.name != observed.name
                or refreshed.comparison_key != observed.comparison_key
                or refreshed.file_identity != observed.file_identity
            ):
                raise CoordinationError(
                    "orphan identity refresh changed the live document binding"
                )
            self._foreign_records[session_uuid] = replace(
                foreign, local_document=refreshed
            )
            return refreshed

    def list_foreign_recoveries(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                foreign.to_public_dict() for foreign in self._foreign_records.values()
            ]

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
            "message": _bounded_text(message, 2048),
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

    def _effective_foreign_public(
        self, foreign: ForeignRecoveryRecord
    ) -> dict[str, Any]:
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
                "message": _bounded_text(str(exc), 2048),
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
            return (
                self._effective_foreign_public(foreign) if foreign is not None else None
            )

    def list_effective_records(self) -> list[dict[str, Any]]:
        """Return redacted effective status for GUI and public RPC reads."""

        with self._lock:
            local = [
                self._effective_public_record(record)
                for record in self._records.values()
            ]
            foreign = [
                self._effective_foreign_public(record)
                for record in self._foreign_records.values()
            ]
            return local + foreign
