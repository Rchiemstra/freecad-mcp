"""Pure, read-only decoders for historic version-2 lease records.

This compatibility module deliberately has no FreeCAD or Qt dependency.  It
retains the retired wire shape, but exposes no transition or revision authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType as _MappingProxyType
from typing import Any
from typing import Self as _Self

from .types.document_identity import DocumentIdentity
from .types.document_selector import DocumentSelector  # noqa: F401
from .types.file_baseline import FileBaseline
from .types.file_identity import FileIdentity  # noqa: F401
from .types.invalid_transition_error import InvalidTransitionError  # noqa: F401
from .types.lease_credential import LeaseCredential  # noqa: F401
from .types.lease_error_info import LeaseErrorInfo
from .types.lease_model_error import LeaseModelError  # noqa: F401
from .types.lease_owner import LeaseOwner
from .types.lease_state import LeaseState
from .types.live_document_validation import LiveDocumentValidation  # noqa: F401
from .types.save_as_migration import SaveAsMigration
from .types.save_as_migration_role import SaveAsMigrationRole  # noqa: F401
from .types.schema_constants import (
    MAX_PERSISTED_TASK_SUMMARY_CHARS,  # noqa: F401
    RECORD_KIND,
    SCHEMA_VERSION,
)
from .types.task_summary import sanitize_persisted_task_summary
from .types.time_utils import utc_now
from .types.token_utils import (  # noqa: F401
    TOKEN_FINGERPRINT_RE,
    token_fingerprint,
    token_matches,
)
from .types.transitions import (  # noqa: F401
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
)

_HISTORIC_REDACTED_FIELD_NAMES = frozenset(
    {
        "current_operation",
        "error",
        "message",
        "request_id",
        "task_summary",
        "token_fingerprint",
    }
)
_HISTORIC_SENSITIVE_MARKERS = frozenset(
    {
        "authorization",
        "bearer",
        "capability",
        "credential",
        "diagnostic",
        "grant",
        "permission",
        "secret",
        "token",
    }
)
_INVALID_HISTORIC_PAYLOAD = object()


def _freeze_historic_value(value: Any) -> Any:
    """Return a recursively immutable copy of a historic JSON value."""

    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("historic sidecar mapping keys must be strings")
        return _MappingProxyType(
            {key: _freeze_historic_value(item) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze_historic_value(item) for item in value)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(
        f"historic sidecar contains unsupported value {type(value).__name__}"
    )


def _thaw_historic_value(value: Any) -> Any:
    """Return a fresh mutable copy of a recursively frozen historic value."""

    if isinstance(value, Mapping):
        return {key: _thaw_historic_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_historic_value(item) for item in value]
    if isinstance(value, frozenset):
        return {_thaw_historic_value(item) for item in value}
    return value


def _historic_hash(value: Any) -> int:
    """Hash immutable historic data without retaining mutable containers."""

    if isinstance(value, Mapping):
        return hash(
            frozenset((key, _historic_hash(item)) for key, item in value.items())
        )
    if isinstance(value, tuple):
        return hash(tuple(_historic_hash(item) for item in value))
    return hash(value)


def _redact_historic_public_value(value: Any) -> Any:
    """Copy historic data while removing secret-bearing diagnostic fields."""

    if isinstance(value, Mapping):
        return {
            key: _redact_historic_public_value(item)
            for key, item in value.items()
            if key.casefold() not in _HISTORIC_REDACTED_FIELD_NAMES
            and not any(
                marker in "".join(character for character in key.casefold() if character.isalnum())
                for marker in _HISTORIC_SENSITIVE_MARKERS
            )
        }
    if isinstance(value, tuple):
        return [_redact_historic_public_value(item) for item in value]
    if isinstance(value, str):
        normalized = "".join(
            character for character in value.casefold() if character.isalnum()
        )
        if any(marker in normalized for marker in _HISTORIC_SENSITIVE_MARKERS):
            return "<redacted>"
    return value


def _validated_historic_payload(data: Any) -> Mapping[str, Any] | object:
    """Return fully schema-validated historic data or an opaque invalid sentinel."""

    # Local imports avoid a model/validator import cycle while keeping this public
    # mapping decoder subject to the exact same schema as the byte decoder.
    from .sidecar_ops.validate_payload import validate_sidecar_payload
    from .sidecar_types.sidecar_malformed_error import SidecarMalformedError

    try:
        return validate_sidecar_payload(data)
    except (KeyError, RecursionError, TypeError, ValueError, SidecarMalformedError):
        return _INVALID_HISTORIC_PAYLOAD


@dataclass(frozen=True, slots=True, repr=False, init=False)
class HistoricLeaseRecord:
    """Read-only decoded sidecar data retained solely for compatibility.

    This value deliberately preserves historic serialized data without creating
    a live lease record.  It has no transition, revision, credential, or
    authorization API.
    """

    _payload: Mapping[str, Any] = field(repr=False)

    def __new__(cls) -> _Self:
        raise TypeError("HistoricLeaseRecord must be created by its decoder")

    def __repr__(self) -> str:
        return "HistoricLeaseRecord(<redacted>)"

    def __hash__(self) -> int:
        return _historic_hash(self._payload)

    def to_sidecar_dict(self) -> dict[str, Any]:
        """Return a fresh mutable copy of the historic sidecar mapping."""

        return _thaw_historic_value(self._payload)

    def to_public_dict(self) -> dict[str, Any]:
        """Return historic status data without credentials or diagnostics."""

        return _redact_historic_public_value(self._payload)


def decode_historic_lease_record(data: Mapping[str, Any]) -> HistoricLeaseRecord:
    """Decode a historic sidecar mapping into immutable compatibility data.

    The decoder only snapshots an already-serialized historic shape.  It does
    not instantiate a live lease, validate a transition, or confer authority.
    """

    validated = _validated_historic_payload(data)
    if validated is _INVALID_HISTORIC_PAYLOAD:
        raise ValueError("historic sidecar record is invalid")

    record = object.__new__(HistoricLeaseRecord)
    object.__setattr__(record, "_payload", _freeze_historic_value(validated))
    return record


@dataclass(frozen=True, slots=True)
class LeaseRecord:
    """Read-only compatibility projection of a validated schema-v2 record.

    The class remains importable for historic callers and byte decoding.  It
    cannot revise or transition the retired lease state machine.
    """

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
        """Return the historic wire representation with privacy-safe diagnostics.

        A task summary is omitted unless an explicit compatibility decoder caller
        requests it.  The frozen record is never modified.
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
        """Return historic data without credentials or diagnostic contents."""

        return _redact_historic_public_value(
            self.to_sidecar_dict(include_task_summary=True)
        )

    @classmethod
    def from_sidecar_dict(cls, data: Mapping[str, Any]) -> LeaseRecord:
        """Decode a validated historic mapping into a frozen compatibility value."""

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
