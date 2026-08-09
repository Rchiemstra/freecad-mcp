"""Authoritative verified save result."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

try:
    from document_lease.model import FileBaseline
except ImportError:
    from addon.FreeCADMCP.document_lease.model import FileBaseline

from .archive_verification import ArchiveVerification


@dataclass(frozen=True)
class SaveResult:
    """Authoritative result returned only after the saved FCStd was verified."""

    mode: str
    path: str
    previous_path: str | None
    baseline: FileBaseline
    archive: ArchiveVerification
    validation_profile: str = "default"
    domain_validation: Mapping[str, Any] = field(default_factory=dict)
    destination_preexisted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "mode": self.mode,
            "path": self.path,
            "previous_path": self.previous_path,
            "baseline": self.baseline.to_dict(),
            "archive": self.archive.to_dict(),
            "validation_profile": self.validation_profile,
            "domain_validation": dict(self.domain_validation),
            "destination_preexisted": self.destination_preexisted,
        }

SaveResult.__module__ = "rpc_server.save_service"
