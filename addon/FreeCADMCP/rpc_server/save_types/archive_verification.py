"""FCStd archive verification result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_REQUIRED_MEMBERS = ("Document.xml",)


@dataclass(frozen=True)
class ArchiveVerification:
    member_count: int
    uncompressed_size: int
    required_members: tuple[str, ...] = DEFAULT_REQUIRED_MEMBERS

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_count": self.member_count,
            "uncompressed_size": self.uncompressed_size,
            "required_members": list(self.required_members),
        }

ArchiveVerification.__module__ = "rpc_server.save_service"
