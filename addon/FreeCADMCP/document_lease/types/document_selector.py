from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentSelector:
    document_session_uuid: str | None = None
    document_name: str | None = None
    canonical_path: str | None = None

DocumentSelector.__module__ = "document_lease.model"
