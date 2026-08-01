"""Pure data model for version-2 per-document leases.

This module deliberately has no FreeCAD or Qt dependency.  It owns the wire
shape and transition rules, while :mod:`service` is the only component that
commits transitions for live leases.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from .types.document_identity import DocumentIdentity

# §3.3 compatibility shims — keep old import paths working.
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
from .types.token_utils import TOKEN_FINGERPRINT_RE, token_fingerprint, token_matches  # noqa: F401
from .types.transitions import (  # noqa: F401
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    validate_transition,
)


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
