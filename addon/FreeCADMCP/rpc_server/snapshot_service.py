"""GUI-thread FCStd snapshots for isolated read-only workers."""

from __future__ import annotations

import os
from pathlib import Path

import FreeCAD
import FreeCADGui

try:
    from document_lease.sidecar import (
        _harden_directory_permissions,
        _harden_permissions,
    )
except ImportError:
    from addon.FreeCADMCP.document_lease.sidecar import (
        _harden_directory_permissions,
        _harden_permissions,
    )

from .snapshot_service_ops.baseline_snapshot import (
    create_lease_baseline_snapshot_gui,
    discard_lease_baseline_snapshot,
)
from .snapshot_service_ops.create_snapshot_bundle import (
    create_primary_snapshot_gui,
    create_snapshot_bundle_gui,
)
from .snapshot_service_ops.document_state_helpers import selection_state
from .snapshot_service_ops.link_manifest import collect_link_manifest
from .snapshot_service_ops.materialize_aliases import materialize_load_aliases
from .snapshot_service_ops.recovery_paths import (
    _default_recovery_root,
    recovery_snapshot_path,
)
from .snapshot_service_ops.restore_snapshot import restore_snapshot_in_place_gui
from .snapshot_service_ops.snapshot_restore_error import SnapshotRestoreError

# §3.3 compatibility shims for deep test imports.
_selection_state = selection_state
_collect_link_manifest = collect_link_manifest
_recovery_root = _default_recovery_root

__all__ = [
    "FreeCAD",
    "FreeCADGui",
    "Path",
    "SnapshotRestoreError",
    "_harden_directory_permissions",
    "_harden_permissions",
    "_recovery_root",
    "create_lease_baseline_snapshot_gui",
    "create_primary_snapshot_gui",
    "create_snapshot_bundle_gui",
    "discard_lease_baseline_snapshot",
    "materialize_load_aliases",
    "os",
    "recovery_snapshot_path",
    "restore_snapshot_in_place_gui",
]
