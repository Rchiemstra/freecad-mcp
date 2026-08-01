from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .file_identity import FileIdentity


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

FileBaseline.__module__ = "document_lease.model"
