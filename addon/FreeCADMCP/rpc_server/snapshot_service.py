"""GUI-thread FCStd snapshots for isolated read-only workers."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import FreeCAD
import FreeCADGui

from .snapshot_service_ops.create_snapshot_bundle import (
    create_primary_snapshot_gui,
    create_snapshot_bundle_gui,
)
from .snapshot_service_ops.document_state_helpers import selection_state
from .snapshot_service_ops.link_manifest import collect_link_manifest
from .snapshot_service_ops.materialize_aliases import materialize_load_aliases
from .snapshot_service_ops.restore_snapshot import restore_snapshot_in_place_gui
from .snapshot_service_ops.snapshot_restore_error import SnapshotRestoreError

# §3.3 compatibility shims for deep test imports.
_selection_state = selection_state
_collect_link_manifest = collect_link_manifest


def _harden_permissions(path, *, strict):
    """Apply owner-only permissions to a worker snapshot file."""

    try:
        os.chmod(path, 0o600)
        if os.name != "nt" and stat.S_IMODE(Path(path).stat().st_mode) != 0o600:
            raise OSError("snapshot file mode is not 0600")
    except OSError:
        if strict:
            raise


def _harden_directory_permissions(path, *, strict):
    """Apply owner-only permissions to a worker snapshot directory."""

    try:
        target = Path(path)
        if not target.is_dir():
            raise OSError("snapshot directory target is not a directory")
        os.chmod(target, 0o700)
        if os.name != "nt" and stat.S_IMODE(target.stat().st_mode) != 0o700:
            raise OSError("snapshot directory mode is not 0700")
    except OSError:
        if strict:
            raise

__all__ = [
    "FreeCAD",
    "FreeCADGui",
    "Path",
    "SnapshotRestoreError",
    "_harden_directory_permissions",
    "_harden_permissions",
    "create_primary_snapshot_gui",
    "create_snapshot_bundle_gui",
    "materialize_load_aliases",
    "os",
    "restore_snapshot_in_place_gui",
]
