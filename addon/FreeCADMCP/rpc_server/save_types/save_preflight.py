"""Filesystem preflight evidence for save operations."""

from __future__ import annotations

from dataclasses import dataclass

try:
    from document_lease.model import FileBaseline
except ImportError:
    from addon.FreeCADMCP.document_lease.model import FileBaseline


@dataclass(frozen=True)
class SavePreflight:
    """Filesystem evidence captured outside FreeCAD's GUI thread."""

    mode: str
    path: str
    comparison_key: str
    previous_path: str | None
    previous_comparison_key: str | None
    source_baseline: FileBaseline | None
    validation_profile: str = "default"
    destination_preexisted: bool = False
    destination_baseline: FileBaseline | None = None

SavePreflight.__module__ = "rpc_server.save_service"
