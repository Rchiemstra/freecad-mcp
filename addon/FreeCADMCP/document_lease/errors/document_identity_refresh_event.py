"""Token-free audit record for an automatic same-path identity refresh."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DocumentIdentityRefreshEvent:
    """Token-free audit record for an automatic same-path identity refresh."""

    at: str
    trigger: str
    document_session_uuid: str
    document_name: str
    canonical_path: str | None
    lease_state: str
    lease_id: str
    generation: int
    previous_file_identity: dict[str, Any] | None
    refreshed_file_identity: dict[str, Any] | None
    baseline_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "trigger": self.trigger,
            "document_session_uuid": self.document_session_uuid,
            "document_name": self.document_name,
            "canonical_path": self.canonical_path,
            "lease_state": self.lease_state,
            "lease_id": self.lease_id,
            "generation": self.generation,
            "previous_file_identity": self.previous_file_identity,
            "refreshed_file_identity": self.refreshed_file_identity,
            "baseline_sha256": self.baseline_sha256,
        }


DocumentIdentityRefreshEvent.__module__ = "document_lease.service"
