"""Lease credential grant returned from acquisition and recovery paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..model import LeaseCredential, LeaseRecord


@dataclass(frozen=True)
class LeaseGrant:
    credential: LeaseCredential
    record: LeaseRecord
    coordination_uncertain: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Acquisition is the sole serialization that contains the raw token."""

        result = self.record.to_public_dict()
        result["credential"] = {
            "lease_id": self.credential.lease_id,
            "document_session_uuid": self.credential.document_session_uuid,
            "generation": self.credential.generation,
            "token": self.credential.token,
        }
        if self.coordination_uncertain:
            result["coordination_uncertain"] = True
            result["warning_code"] = "SIDECAR_COMMIT_UNCERTAIN"
        return result


LeaseGrant.__module__ = "document_lease.service"
