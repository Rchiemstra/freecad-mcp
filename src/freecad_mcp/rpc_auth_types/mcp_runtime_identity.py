"""Extracted ``McpRuntimeIdentity`` for ARCH002 (workstream 1G)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .validation import (
    _format_utc,
    _parse_utc,
    _require_identifier,
    _require_pid,
    _require_uuid,
)


@dataclass(frozen=True)
class McpRuntimeIdentity:
    runtime_id: str
    pid: int
    process_started_at: str
    hostname: str
    client_build_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "runtime_id", _require_uuid(self.runtime_id, "mcp.runtime_id")
        )
        _require_pid(self.pid, "mcp.pid")
        object.__setattr__(
            self,
            "process_started_at",
            _format_utc(_parse_utc(self.process_started_at, "mcp.process_started_at")),
        )
        _require_identifier(self.hostname, "mcp.hostname")
        _require_identifier(self.client_build_id, "mcp.client_build_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "pid": self.pid,
            "process_started_at": self.process_started_at,
            "hostname": self.hostname,
            "client_build_id": self.client_build_id,
        }


McpRuntimeIdentity.__module__ = "freecad_mcp.rpc_auth"
