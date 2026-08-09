from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LeaseOwner:
    addon_profile_id: str
    addon_runtime_id: str
    freecad_pid: int
    freecad_process_started_at: str
    boot_id: str
    mcp_instance_id: str
    mcp_pid: int
    mcp_process_started_at: str
    hostname: str
    mcp_hostname: str = ""
    client: str = ""
    agent_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "addon_profile_id": self.addon_profile_id,
            "addon_runtime_id": self.addon_runtime_id,
            "freecad_pid": self.freecad_pid,
            "freecad_process_started_at": self.freecad_process_started_at,
            "boot_id": self.boot_id,
            "mcp_instance_id": self.mcp_instance_id,
            "mcp_pid": self.mcp_pid,
            "mcp_process_started_at": self.mcp_process_started_at,
            "hostname": self.hostname,
            "mcp_hostname": self.mcp_hostname,
            "client": self.client,
            "agent_id": self.agent_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LeaseOwner:
        return cls(
            **{
                name: data.get(name, "") if name == "mcp_hostname" else data[name]
                for name in cls.__dataclass_fields__
            }
        )

LeaseOwner.__module__ = "document_lease.model"
