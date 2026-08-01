"""Lease baseline snapshot create/discard."""

from __future__ import annotations

import os
from contextlib import suppress

from .recovery_paths import recovery_snapshot_path
from .sidecar_permissions import harden_permissions
from .snapshot_save_context import internal_snapshot_save_observer_scope


def create_lease_baseline_snapshot_gui(
    document,
    *,
    observer_request_id: str = "",
) -> str:
    """Persist an owner-only recovery saveCopy and return only its opaque ID."""
    import uuid

    snapshot_id = str(uuid.uuid4())
    target = recovery_snapshot_path(snapshot_id)
    if os.path.lexists(target):
        raise RuntimeError("recovery snapshot identifier collision")
    # FreeCAD's saveCopy appends ``.FCStd`` when the requested filename does
    # not already end in that extension.  Keep the temporary marker before the
    # extension so the file is created at the exact path we later harden,
    # fsync, and atomically replace.
    temporary = target.with_name(f"{target.stem}.tmp{target.suffix}")
    if os.path.lexists(temporary):
        raise RuntimeError("recovery snapshot temporary path already exists")
    try:
        with internal_snapshot_save_observer_scope(
            document,
            temporary,
            observer_request_id,
        ):
            document.saveCopy(str(temporary))
        harden_permissions(temporary, strict=True)
        with temporary.open("r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        harden_permissions(target, strict=True)
    except Exception:
        with suppress(OSError):
            temporary.unlink()
        raise
    return snapshot_id


def discard_lease_baseline_snapshot(snapshot_id: str) -> None:
    target = recovery_snapshot_path(snapshot_id)
    with suppress(FileNotFoundError):
        target.unlink()
