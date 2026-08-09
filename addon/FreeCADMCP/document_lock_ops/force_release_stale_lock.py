from __future__ import annotations

import contextlib
import os
from typing import Any

from .facade_surfaces import current_time, resolve_pid_alive
from .lease_record import LeaseRecord
from .registry_queries import _is_stale
from .registry_state import _registry, _registry_lock
from .sidecar_io import _read_sidecar, _remove_sidecar, sidecar_path_for


def force_release_stale_lock(doc_key: str) -> dict[str, Any]:
    """Remove a stale lock only after verifying the owning pid is dead."""
    now = current_time()
    side = None
    record: LeaseRecord | None = None

    with _registry_lock:
        record = _registry.get(doc_key)

    is_path_key = os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd")
    if is_path_key:
        side = sidecar_path_for(doc_key)
        side_data = _read_sidecar(side)
        if side_data:
            with contextlib.suppress(TypeError):
                record = LeaseRecord.from_dict(side_data)

    if record is None:
        return {
            "success": False,
            "error_code": "document_not_locked",
            "error": "No lock found to force-release",
        }

    if not _is_stale(record, now=now):
        return {
            "success": False,
            "error_code": "lock_not_stale",
            "error": "Lease heartbeat has not expired",
            "lease": record.to_dict(),
        }

    if resolve_pid_alive(record.pid):
        return {
            "success": False,
            "error_code": "owner_still_alive",
            "error": (
                f"Owning pid {record.pid} is still alive; refusing to force-release"
            ),
            "lease": record.to_dict(),
        }

    with _registry_lock:
        _registry.pop(doc_key, None)
    if side is not None:
        _remove_sidecar(side)
    return {"success": True, "released": doc_key, "was_stale": True, "lease": record.to_dict()}
