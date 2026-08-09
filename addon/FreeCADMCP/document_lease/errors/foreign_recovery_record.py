"""Immutable association between a local open document and foreign authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..model import DocumentIdentity, LeaseRecord


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


ForeignRecoveryRecord.__module__ = "document_lease.service"
