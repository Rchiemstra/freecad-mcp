"""Authoritative in-process registry for version-2 document leases."""

from __future__ import annotations

import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

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
    LeaseCredential,
    LeaseErrorInfo,
    LiveDocumentValidation,
    LeaseOwner,
    LeaseRecord,
    LeaseState,
    SaveAsMigration,
    SaveAsMigrationRole,
    token_fingerprint,
    token_matches,
    utc_now,
)
from .sidecar import (
    SidecarError,
    SidecarStore,
    sidecar_path_for,
)


DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 10.0
DEFAULT_SIDECAR_HEARTBEAT_INTERVAL_SECONDS = 30.0
DEFAULT_STALE_AFTER_SECONDS = 90.0


class LeaseServiceError(RuntimeError):
    code = "LEASE_SERVICE_ERROR"

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None):
        self.details = dict(details or {})
        super().__init__(message)


class LeaseConflictError(LeaseServiceError):
    code = "LEASE_CONFLICT"


class AuthorizationError(LeaseServiceError):
    code = "LEASE_AUTHORIZATION_FAILED"


class LeaseStateError(LeaseServiceError):
    code = "LEASE_STATE_FORBIDS_OPERATION"


class CoordinationError(LeaseServiceError):
    code = "LEASE_COORDINATION_LOST"


class DirtyAcquisitionError(LeaseServiceError):
    code = "DIRTY_REQUIRES_LOCAL_ADOPTION"


class CleanReleaseError(LeaseServiceError):
    code = "CLEAN_RELEASE_PRECONDITION_FAILED"


class LiveDocumentValidationError(CleanReleaseError):
    """The live document or saved file no longer matches lease authority."""

    code = "LIVE_DOCUMENT_VALIDATION_FAILED"


class LocalRecoveryError(LeaseServiceError):
    """A confirmed local GUI recovery action could not complete safely."""

    code = "LOCAL_RECOVERY_FAILED"


class ForeignRecoveryError(LocalRecoveryError):
    """A persisted foreign record could not be imported or fenced safely."""

    code = "FOREIGN_RECOVERY_UNSAFE"


@dataclass(frozen=True)
class LeaseGrant:
    credential: LeaseCredential
    record: LeaseRecord

    def to_dict(self) -> dict[str, Any]:
        """Acquisition is the sole serialization that contains the raw token."""

        result = self.record.to_public_dict()
        result["credential"] = {
            "lease_id": self.credential.lease_id,
            "document_session_uuid": self.credential.document_session_uuid,
            "generation": self.credential.generation,
            "token": self.credential.token,
        }
        return result


@dataclass(frozen=True)
class ProcessLivenessEvidence:
    """Result of a trusted same-host process identity probe.

    ``exists=None`` means the probe could not establish either liveness or
    death. A live process must include its observed start timestamp so PID
    reuse can be distinguished from the recorded owner.
    """

    exists: bool | None
    process_started_at: str | None = None


@dataclass(frozen=True)
class LocalRuntimeIdentity:
    """Service-owned identity of the currently running FreeCAD addon."""

    addon_profile_id: str
    addon_runtime_id: str
    freecad_pid: int
    freecad_process_started_at: str
    boot_id: str
    hostname: str


@dataclass(frozen=True)
class ForeignRecoveryRecord:
    """Immutable association between a local open document and foreign authority."""

    local_document: DocumentIdentity
    persisted: LeaseRecord
    imported_at: str

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.persisted.to_public_dict()
        payload["source"] = "foreign_recovery"
        payload["immutable"] = True
        payload["foreign_document_session_uuid"] = self.persisted.document.session_uuid
        payload["local_document"] = self.local_document.to_dict()
        return payload


@dataclass(frozen=True)
class _CancellationContext:
    request_id: str
    previous_state: LeaseState
    previous_operation: str
    mutation_may_have_begun: bool = False


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
        self._effective_error_times: dict[tuple[str, str, int], str] = {}
        self._local_runtime_identity = local_runtime_identity
        self._process_liveness_probe = process_liveness_probe
        self._lock = threading.RLock()

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
        self, local: DocumentIdentity, persisted: LeaseRecord
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
        if (
            foreign_document.file_identity != observed_identity
            and not unverified_destination
        ):
            raise ForeignRecoveryError(
                "the adjacent sidecar identifies a different filesystem file"
            )
        if (
            persisted.baseline is not None
            and persisted.baseline.file_identity != foreign_document.file_identity
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
    ) -> LeaseGrant:
        """Publish ACQUIRING before baseline hashing or snapshot creation."""

        identity = self.identity_service.resolve(selector)
        if document_dirty:
            raise DirtyAcquisitionError(
                "a pre-existing dirty document requires local adoption"
            )
        with self._lock:
            existing = self._records.get(identity.session_uuid)
            if existing is not None:
                raise LeaseConflictError(
                    "the live document already has a lease",
                    details=existing.to_public_dict(),
                )
            foreign = self._foreign_records.get(identity.session_uuid)
            if foreign is not None:
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
                dirty=False,
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
            credential = LeaseCredential(
                lease_id=record.lease_id,
                document_session_uuid=identity.session_uuid,
                generation=generation,
                token=raw_token,
                mcp_instance_id=owner.mcp_instance_id,
            )
            return LeaseGrant(credential=credential, record=record)

    def complete_acquisition(
        self,
        credential: LeaseCredential,
        *,
        baseline: FileBaseline | None,
        baseline_validated: bool,
        snapshot_id: str | None,
    ) -> LeaseGrant:
        """Promote only an exact reservation with complete saved-file evidence."""

        with self._lock:
            record = self._record_for_credential(
                credential, allowed_states={LeaseState.ACQUIRING}
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
        """Retain acquisition authority after create/saveCopy cancellation.

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
        missing, mismatched-path, and mismatched-file records are never added
        to the foreign registry and are never rewritten or removed.
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
            self._assert_foreign_document_exact(registered, persisted)
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
                if now - record.monotonic_heartbeat_ns <= self._stale_after_ns:
                    continue
                updated = record.transitioned(
                    LeaseState.STALE,
                    error=LeaseErrorInfo(
                        code="LEASE_STALE",
                        message="Lease heartbeat expired",
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
