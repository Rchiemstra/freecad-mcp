from __future__ import annotations

import hmac
import os
from dataclasses import asdict
from typing import Any

from .eligibility import _is_eligible_target
from .facade_surfaces import current_time, resolve_pid_alive
from .file_baseline import file_baseline
from .lease_record import LeaseRecord
from .lease_state import LeaseState
from .registry_queries import _is_stale
from .registry_state import _registry, _registry_lock, _session_ids
from .sidecar_io import (
    _create_sidecar_exclusive,
    _public_sidecar_payload,
    _read_sidecar,
    _remove_sidecar,
    _write_json_atomic,
    sidecar_path_for,
)


def _destination_sidecar_conflict(
    side_new,
    *,
    expected_fingerprint: str,
) -> dict[str, Any] | None:
    if not side_new.is_file():
        return None
    existing = _read_sidecar(side_new)
    if not existing:
        return None
    if hmac.compare_digest(
        str(existing.get("token_fingerprint") or ""),
        expected_fingerprint,
    ):
        return None
    other = LeaseRecord.from_dict(existing) if existing else None
    if other and not _is_stale(other) and resolve_pid_alive(other.pid):
        return {
            "success": False,
            "error_code": "document_locked_by_other",
            "error": "Destination path already locked by another instance",
            "lease": other.to_dict(),
        }
    return {
        "success": False,
        "error_code": "stale_lock_recovery_required",
        "error": (
            "Destination sidecar requires confirmed local recovery; "
            "Save As did not alter it"
        ),
        "lease": other.to_dict() if other else None,
    }


def migrate_lease_key(old_key: str, new_key: str, *, doc_name: str | None = None) -> dict[str, Any]:
    """Transfer an active lease from UUID/old path to a new path without unlocking."""
    if not (os.path.isabs(new_key) and new_key.lower().endswith(".fcstd")):
        return {
            "success": False,
            "error_code": "invalid_destination",
            "error": "Destination key must be an absolute .FCStd path",
        }
    if not _is_eligible_target(new_key):
        return {
            "success": False,
            "error_code": "ineligible_target",
            "error": f"Destination is not eligible: {new_key}",
        }

    with _registry_lock:
        record = _registry.get(old_key)
        if record is None:
            return {
                "success": False,
                "error_code": "document_not_locked",
                "error": "No lease to migrate",
            }
        migrated = LeaseRecord(
            **{
                **asdict(record),
                "doc_key": new_key,
                "doc_name": doc_name or record.doc_name,
                "state": LeaseState.LOCKED_SAVING.value,
                "last_heartbeat": current_time(),
            }
        )
        mtime, digest = file_baseline(new_key)
        migrated.baseline_mtime = mtime
        migrated.baseline_hash = digest
        migrated.last_save_time = current_time()
        migrated.state = LeaseState.LOCKED_IDLE.value
        migrated.document_dirty = False
        migrated.last_verified_save_revision = migrated.last_mutation_revision

        side_new = sidecar_path_for(new_key)
        expected_fingerprint = record.to_sidecar_dict()["token_fingerprint"]
        if conflict := _destination_sidecar_conflict(
            side_new, expected_fingerprint=expected_fingerprint
        ):
            return conflict

        if not _create_sidecar_exclusive(side_new, migrated.to_sidecar_dict()):
            existing = _read_sidecar(side_new)
            if existing and hmac.compare_digest(
                str(existing.get("token_fingerprint") or ""),
                expected_fingerprint,
            ):
                _write_json_atomic(side_new, migrated.to_sidecar_dict())
            else:
                return {
                    "success": False,
                    "error_code": "document_locked_by_other",
                    "error": "Could not create destination sidecar",
                    "lease": _public_sidecar_payload(existing),
                }

        _registry[new_key] = migrated
        _registry.pop(old_key, None)
        if doc_name:
            _session_ids.pop(doc_name, None)

    if os.path.isabs(old_key) and old_key.lower().endswith(".fcstd"):
        _remove_sidecar(sidecar_path_for(old_key))

    return {"success": True, "lease": migrated.to_dict(), "old_key": old_key, "new_key": new_key}
