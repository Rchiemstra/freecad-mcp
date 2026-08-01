from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .file_identity import FileIdentity


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

DocumentIdentity.__module__ = "document_lease.model"
