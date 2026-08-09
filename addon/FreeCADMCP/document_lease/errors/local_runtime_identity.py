"""Service-owned identity of the currently running FreeCAD addon."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocalRuntimeIdentity:
    """Service-owned identity of the currently running FreeCAD addon."""

    addon_profile_id: str
    addon_runtime_id: str
    freecad_pid: int
    freecad_process_started_at: str
    boot_id: str
    hostname: str


LocalRuntimeIdentity.__module__ = "document_lease.service"
