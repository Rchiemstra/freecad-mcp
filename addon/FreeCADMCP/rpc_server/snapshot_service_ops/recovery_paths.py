"""Recovery snapshot path resolution."""

from __future__ import annotations

import uuid
from pathlib import Path

import FreeCAD

from .sidecar_permissions import harden_directory_permissions

RECOVERY_DIRECTORY = "FreeCADMCPRecovery"


def _default_recovery_root() -> Path:
    root = Path(FreeCAD.getUserAppDataDir()) / RECOVERY_DIRECTORY
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    harden_directory_permissions(root, strict=True)
    return root


def recovery_root() -> Path:
    from ..snapshot_service import _recovery_root

    return _recovery_root()


def recovery_snapshot_path(snapshot_id: str) -> Path:
    """Resolve an opaque snapshot ID without accepting caller-supplied paths."""
    normalized = str(uuid.UUID(str(snapshot_id)))
    return recovery_root() / f"{normalized}.FCStd"
