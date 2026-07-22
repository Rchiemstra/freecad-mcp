"""Pure data model for version-2 per-document leases.

This module deliberately has no FreeCAD or Qt dependency.  It owns the wire
shape and transition rules, while :mod:`service` is the only component that
commits transitions for live leases.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


SCHEMA_VERSION = 2
RECORD_KIND = "freecad-mcp-document-lease"
TOKEN_FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_PERSISTED_TASK_SUMMARY_CHARS = 256


def sanitize_persisted_task_summary(value: str | None) -> str:
    """Return a single-line, bounded sidecar-safe diagnostic summary.

    Task metadata can contain prompts, customer details, or terminal control
    characters.  Persistence is therefore opt-in and, even when enabled, uses
    a deliberately smaller representation than the in-memory/public-status
    value.  Unicode control/format/surrogate characters and all whitespace are
    normalized to ordinary spaces before the length cap is applied.
    """

    if not value:
        return ""
    characters: list[str] = []
    pending_space = False
    for character in str(value):
        if character.isspace() or unicodedata.category(character).startswith("C"):
            pending_space = bool(characters)
            continue
        if pending_space:
            if len(characters) >= MAX_PERSISTED_TASK_SUMMARY_CHARS:
                break
            characters.append(" ")
            pending_space = False
        if len(characters) >= MAX_PERSISTED_TASK_SUMMARY_CHARS:
            break
        characters.append(character)
    return "".join(characters).rstrip()


class LeaseState(str, Enum):
    ACQUIRING = "ACQUIRING"
    LOCKED_IDLE = "LOCKED_IDLE"
    LOCKED_EDITING = "LOCKED_EDITING"
    LOCKED_RECOMPUTING = "LOCKED_RECOMPUTING"
    LOCKED_SAVING = "LOCKED_SAVING"
    LOCKED_ERROR = "LOCKED_ERROR"
    USER_INTERVENED = "USER_INTERVENED"
    CANCELLING = "CANCELLING"
    RELEASING = "RELEASING"
    UNLOCKED_SAVED = "UNLOCKED_SAVED"
    UNLOCKED_DIRTY = "UNLOCKED_DIRTY"
    STALE = "STALE"


class SaveAsMigrationRole(str, Enum):
    """The side of an in-flight Save As represented by one sidecar."""

    SOURCE = "source"
    DESTINATION = "destination"


TERMINAL_STATES = frozenset(
    {LeaseState.UNLOCKED_SAVED, LeaseState.UNLOCKED_DIRTY}
)


# The transition table is intentionally explicit.  Recovery paths are present,
# but no heartbeat or client-supplied state is involved in choosing one.
ALLOWED_TRANSITIONS: Mapping[LeaseState, frozenset[LeaseState]] = {
    LeaseState.ACQUIRING: frozenset(
        {LeaseState.LOCKED_IDLE, LeaseState.LOCKED_ERROR, LeaseState.STALE}
    ),
    LeaseState.LOCKED_IDLE: frozenset(
        {
            LeaseState.LOCKED_EDITING,
            LeaseState.LOCKED_RECOMPUTING,
            LeaseState.LOCKED_SAVING,
            LeaseState.LOCKED_ERROR,
            LeaseState.USER_INTERVENED,
            LeaseState.CANCELLING,
            LeaseState.RELEASING,
            LeaseState.STALE,
        }
    ),
    LeaseState.LOCKED_EDITING: frozenset(
        {
            LeaseState.LOCKED_IDLE,
            LeaseState.LOCKED_RECOMPUTING,
            LeaseState.LOCKED_ERROR,
            LeaseState.USER_INTERVENED,
            LeaseState.CANCELLING,
            LeaseState.STALE,
        }
    ),
    LeaseState.LOCKED_RECOMPUTING: frozenset(
        {
            LeaseState.LOCKED_IDLE,
            LeaseState.LOCKED_ERROR,
            LeaseState.USER_INTERVENED,
            LeaseState.CANCELLING,
            LeaseState.STALE,
        }
    ),
    LeaseState.LOCKED_SAVING: frozenset(
        {
            LeaseState.LOCKED_IDLE,
            LeaseState.LOCKED_ERROR,
            LeaseState.USER_INTERVENED,
            LeaseState.CANCELLING,
            LeaseState.STALE,
        }
    ),
    LeaseState.LOCKED_ERROR: frozenset(
        {
            LeaseState.LOCKED_EDITING,
            LeaseState.LOCKED_SAVING,
            LeaseState.USER_INTERVENED,
            LeaseState.CANCELLING,
            LeaseState.UNLOCKED_DIRTY,
            LeaseState.STALE,
        }
    ),
    LeaseState.USER_INTERVENED: frozenset(
        {
            LeaseState.RELEASING,
            LeaseState.UNLOCKED_SAVED,
            LeaseState.UNLOCKED_DIRTY,
            LeaseState.STALE,
        }
    ),
    LeaseState.CANCELLING: frozenset(
        {
            LeaseState.LOCKED_IDLE,
            LeaseState.LOCKED_ERROR,
            LeaseState.USER_INTERVENED,
            LeaseState.STALE,
        }
    ),
    LeaseState.RELEASING: frozenset(
        {LeaseState.UNLOCKED_SAVED, LeaseState.LOCKED_ERROR, LeaseState.STALE}
    ),
    LeaseState.UNLOCKED_SAVED: frozenset({LeaseState.ACQUIRING}),
    LeaseState.UNLOCKED_DIRTY: frozenset(
        {
            LeaseState.RELEASING,
            LeaseState.UNLOCKED_SAVED,
            LeaseState.ACQUIRING,
        }
    ),
    LeaseState.STALE: frozenset(
        {
            LeaseState.LOCKED_IDLE,
            LeaseState.USER_INTERVENED,
            LeaseState.UNLOCKED_SAVED,
            LeaseState.UNLOCKED_DIRTY,
        }
    ),
}


class LeaseModelError(ValueError):
    """Base error for invalid lease model data."""


class InvalidTransitionError(LeaseModelError):
    def __init__(self, current: LeaseState, target: LeaseState):
        self.current = current
        self.target = target
        super().__init__(f"invalid lease transition: {current.value} -> {target.value}")


def validate_transition(current: LeaseState, target: LeaseState) -> None:
    """Raise when *target* is not an explicit successor of *current*."""

    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransitionError(current, target)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def token_fingerprint(token: str) -> str:
    """Return the only token representation allowed in persistent state."""

    if not isinstance(token, str) or not token:
        raise LeaseModelError("lease token must be a non-empty string")
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, fingerprint: str) -> bool:
    """Compare a supplied raw token with a stored SHA-256 fingerprint."""

    if not isinstance(fingerprint, str) or not TOKEN_FINGERPRINT_RE.fullmatch(
        fingerprint
    ):
        return False
    try:
        actual = token_fingerprint(token)
    except LeaseModelError:
        return False
    return hmac.compare_digest(actual, fingerprint)


@dataclass(frozen=True)
class FileIdentity:
    platform: str
    device: int | None = None
    inode: int | None = None
    volume_serial: int | None = None
    file_index: int | None = None

    def comparison_tuple(self) -> tuple[Any, ...]:
        if self.platform == "windows":
            return (self.platform, self.volume_serial, self.file_index)
        return (self.platform, self.device, self.inode)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"platform": self.platform}
        if self.platform == "windows":
            result.update(
                {"volume_serial": self.volume_serial, "file_index": self.file_index}
            )
        else:
            result.update({"device": self.device, "inode": self.inode})
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> FileIdentity | None:
        if data is None:
            return None
        return cls(
            platform=str(data["platform"]),
            device=data.get("device"),
            inode=data.get("inode"),
            volume_serial=data.get("volume_serial"),
            file_index=data.get("file_index"),
        )


@dataclass(frozen=True)
class DocumentIdentity:
    session_uuid: str
    name: str
    canonical_path: str | None = None
    comparison_key: str | None = None
    file_identity: FileIdentity | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_uuid": self.session_uuid,
            "name": self.name,
            "canonical_path": self.canonical_path,
            "comparison_key": self.comparison_key,
            "file_identity": (
                self.file_identity.to_dict() if self.file_identity else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DocumentIdentity:
        return cls(
            session_uuid=str(data["session_uuid"]),
            name=str(data["name"]),
            canonical_path=data.get("canonical_path"),
            comparison_key=data.get("comparison_key"),
            file_identity=FileIdentity.from_dict(data.get("file_identity")),
        )


@dataclass(frozen=True)
class DocumentSelector:
    document_session_uuid: str | None = None
    document_name: str | None = None
    canonical_path: str | None = None


@dataclass(frozen=True)
class SaveAsMigration:
    """Crash-recovery linkage shared by both Save As sidecars.

    An unsaved first-save has no adjacent source sidecar, so its source path
    pair is null.  A saved-document Save As always persists the source role on
    the source record and the destination role on the destination record.
    """

    migration_id: str
    source_canonical_path: str | None
    source_comparison_key: str | None
    destination_canonical_path: str
    destination_comparison_key: str
    role: SaveAsMigrationRole

    def to_dict(self) -> dict[str, Any]:
        return {
            "migration_id": self.migration_id,
            "source": {
                "canonical_path": self.source_canonical_path,
                "comparison_key": self.source_comparison_key,
            },
            "destination": {
                "canonical_path": self.destination_canonical_path,
                "comparison_key": self.destination_comparison_key,
            },
            "role": self.role.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> SaveAsMigration | None:
        if data is None:
            return None
        source = data["source"]
        destination = data["destination"]
        return cls(
            migration_id=str(data["migration_id"]),
            source_canonical_path=source["canonical_path"],
            source_comparison_key=source["comparison_key"],
            destination_canonical_path=str(destination["canonical_path"]),
            destination_comparison_key=str(destination["comparison_key"]),
            role=SaveAsMigrationRole(data["role"]),
        )


@dataclass(frozen=True)
class LeaseOwner:
    addon_profile_id: str
    addon_runtime_id: str
    freecad_pid: int
    freecad_process_started_at: str
    boot_id: str
    mcp_instance_id: str
    mcp_pid: int
    mcp_process_started_at: str
    hostname: str
    client: str = ""
    agent_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "addon_profile_id": self.addon_profile_id,
            "addon_runtime_id": self.addon_runtime_id,
            "freecad_pid": self.freecad_pid,
            "freecad_process_started_at": self.freecad_process_started_at,
            "boot_id": self.boot_id,
            "mcp_instance_id": self.mcp_instance_id,
            "mcp_pid": self.mcp_pid,
            "mcp_process_started_at": self.mcp_process_started_at,
            "hostname": self.hostname,
            "client": self.client,
            "agent_id": self.agent_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LeaseOwner:
        return cls(**{name: data[name] for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class FileBaseline:
    mtime_ns: int
    size: int
    sha256: str
    file_identity: FileIdentity | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mtime_ns": self.mtime_ns,
            "size": self.size,
            "sha256": self.sha256,
            "file_identity": (
                self.file_identity.to_dict() if self.file_identity else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> FileBaseline | None:
        if data is None:
            return None
        return cls(
            mtime_ns=data["mtime_ns"],
            size=data["size"],
            sha256=str(data["sha256"]),
            file_identity=FileIdentity.from_dict(data.get("file_identity")),
        )


@dataclass(frozen=True)
class LiveDocumentValidation:
    """Fresh addon-owned evidence used for stale recovery and clean release.

    ``document`` must be captured from the currently open FreeCAD document,
    while ``baseline`` describes the file observed immediately before the
    protected operation.  The explicit validation flag prevents an old record
    from being mistaken for new evidence when a caller skipped hashing or
    domain validation.
    """

    document: DocumentIdentity
    document_modified: bool
    baseline: FileBaseline | None
    baseline_validated: bool


@dataclass(frozen=True)
class LeaseErrorInfo:
    code: str
    message: str
    at: str
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "at": self.at,
            "request_id": self.request_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> LeaseErrorInfo | None:
        if data is None:
            return None
        return cls(
            code=str(data["code"]),
            message=str(data["message"]),
            at=str(data["at"]),
            request_id=data.get("request_id"),
        )


@dataclass(frozen=True)
class LeaseCredential:
    lease_id: str
    document_session_uuid: str
    generation: int
    # Credentials may be included in exception context or diagnostic object
    # reprs.  Keep the bearer secret out of those generic representations;
    # acquisition and authenticated wire serialization are the only intended
    # raw-token boundaries.
    token: str = field(repr=False)
    # Populated by the addon from the authenticated transport context, never
    # trusted from the caller's envelope payload.
    mcp_instance_id: str


@dataclass(frozen=True)
class LeaseRecord:
    lease_id: str
    generation: int
    token_fingerprint: str
    document: DocumentIdentity
    owner: LeaseOwner
    state: LeaseState = LeaseState.ACQUIRING
    record_revision: int = 1
    state_revision: int = 1
    acquired_at: str = field(default_factory=utc_now)
    last_heartbeat_at: str = field(default_factory=utc_now)
    heartbeat_sequence: int = 0
    current_operation: str = ""
    task_summary: str = ""
    dirty: bool = False
    user_intervened: bool = False
    last_mutation_revision: int = 0
    last_successful_save_at: str | None = None
    last_verified_save_revision: int = 0
    baseline: FileBaseline | None = None
    error: LeaseErrorInfo | None = None
    validation_complete: bool = False
    snapshot_id: str | None = None
    migration: SaveAsMigration | None = None
    monotonic_heartbeat_ns: int = field(default=0, compare=False, repr=False)

    @property
    def schema_version(self) -> int:
        return SCHEMA_VERSION

    @property
    def record_kind(self) -> str:
        return RECORD_KIND

    def to_sidecar_dict(
        self, *, include_task_summary: bool = False
    ) -> dict[str, Any]:
        """Serialize persistent authority with privacy-safe diagnostics.

        A task summary is omitted unless the caller is the configured sidecar
        store and explicitly opts in.  The in-memory record is never modified.
        """

        return {
            "schema_version": SCHEMA_VERSION,
            "record_kind": RECORD_KIND,
            "record_revision": self.record_revision,
            "lease_id": self.lease_id,
            "generation": self.generation,
            "token_fingerprint": self.token_fingerprint,
            "migration": self.migration.to_dict() if self.migration else None,
            "document": self.document.to_dict(),
            "owner": self.owner.to_dict(),
            "lease": {
                "state": self.state.value,
                "state_revision": self.state_revision,
                "acquired_at": self.acquired_at,
                "last_heartbeat_at": self.last_heartbeat_at,
                "heartbeat_sequence": self.heartbeat_sequence,
                "current_operation": self.current_operation,
                "task_summary": (
                    sanitize_persisted_task_summary(self.task_summary)
                    if include_task_summary
                    else ""
                ),
            },
            "document_state": {
                "dirty": self.dirty,
                "user_intervened": self.user_intervened,
                "last_mutation_revision": self.last_mutation_revision,
                "last_successful_save_at": self.last_successful_save_at,
                "last_verified_save_revision": self.last_verified_save_revision,
                "baseline": self.baseline.to_dict() if self.baseline else None,
                "error": self.error.to_dict() if self.error else None,
                "validation_complete": self.validation_complete,
                "snapshot_id": self.snapshot_id,
            },
        }

    def to_public_dict(self) -> dict[str, Any]:
        """Return status metadata with both raw token and digest omitted."""

        payload = self.to_sidecar_dict()
        payload.pop("token_fingerprint", None)
        # Public status is sourced from the process-local registry. Keep its
        # already-bounded task metadata useful without coupling it to the
        # separate, opt-in persistence policy.
        payload["lease"]["task_summary"] = self.task_summary
        return payload

    @classmethod
    def from_sidecar_dict(cls, data: Mapping[str, Any]) -> LeaseRecord:
        lease = data["lease"]
        document_state = data["document_state"]
        return cls(
            lease_id=str(data["lease_id"]),
            generation=data["generation"],
            token_fingerprint=str(data["token_fingerprint"]),
            migration=SaveAsMigration.from_dict(data.get("migration")),
            document=DocumentIdentity.from_dict(data["document"]),
            owner=LeaseOwner.from_dict(data["owner"]),
            state=LeaseState(lease["state"]),
            record_revision=data["record_revision"],
            state_revision=lease["state_revision"],
            acquired_at=str(lease["acquired_at"]),
            last_heartbeat_at=str(lease["last_heartbeat_at"]),
            heartbeat_sequence=lease["heartbeat_sequence"],
            current_operation=str(lease["current_operation"]),
            task_summary=str(lease["task_summary"]),
            dirty=document_state["dirty"],
            user_intervened=document_state["user_intervened"],
            last_mutation_revision=document_state["last_mutation_revision"],
            last_successful_save_at=document_state["last_successful_save_at"],
            last_verified_save_revision=document_state[
                "last_verified_save_revision"
            ],
            baseline=FileBaseline.from_dict(document_state["baseline"]),
            error=LeaseErrorInfo.from_dict(document_state["error"]),
            validation_complete=document_state["validation_complete"],
            snapshot_id=document_state["snapshot_id"],
        )

    def transitioned(self, target: LeaseState, **changes: Any) -> LeaseRecord:
        """Return a revisioned successor after validating the state edge."""

        validate_transition(self.state, target)
        return replace(
            self,
            state=target,
            state_revision=self.state_revision + 1,
            record_revision=self.record_revision + 1,
            **changes,
        )

    def revised(self, **changes: Any) -> LeaseRecord:
        """Return a non-state metadata revision."""

        return replace(self, record_revision=self.record_revision + 1, **changes)
