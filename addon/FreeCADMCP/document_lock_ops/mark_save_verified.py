from __future__ import annotations

import hmac
import os
from typing import Any

from .facade_surfaces import current_time
from .lease_state import LeaseState
from .registry_state import _registry, _registry_lock
from .sidecar_io import _read_sidecar, _write_json_atomic, sidecar_path_for


def _validate_save_sidecar(
    doc_key: str,
    *,
    expected_lease_id: str,
    expected_generation: int,
    expected_fingerprint: str,
) -> dict[str, Any] | None:
    side = sidecar_path_for(doc_key)
    persisted = _read_sidecar(side)
    try:
        persisted_generation = int(persisted.get("generation", 0))
    except (AttributeError, TypeError, ValueError):
        persisted_generation = 0
    if (
        not persisted
        or "schema_version" in persisted
        or "record_kind" in persisted
        or persisted.get("lease_id") != expected_lease_id
        or persisted_generation != expected_generation
        or not hmac.compare_digest(
            str(persisted.get("token_fingerprint", "")),
            str(expected_fingerprint),
        )
    ):
        return {
            "success": False,
            "error_code": "sidecar_replaced",
            "error": (
                "The compatibility sidecar changed before save promotion; "
                "writes remain blocked"
            ),
        }
    return None


def mark_save_verified(
    doc_key: str,
    token: str,
    *,
    baseline_mtime: float,
    baseline_hash: str,
) -> dict[str, Any]:
    """Promote a compatibility-v1 save after off-thread file verification."""
    with _registry_lock:
        record = _registry.get(doc_key)
        if record is None:
            return {
                "success": False,
                "error_code": "document_not_locked",
                "error": "No active lease for this document",
            }
        if not token or not hmac.compare_digest(str(record.token), str(token)):
            return {
                "success": False,
                "error_code": "invalid_lease_token",
                "error": "Lease token does not match",
                "lease": record.to_dict(),
            }
        if record.state not in {
            LeaseState.LOCKED_SAVING.value,
            LeaseState.LOCKED_IDLE.value,
        }:
            return {
                "success": False,
                "error_code": "lease_state_blocks_save_promotion",
                "error": f"Cannot promote a verified save from {record.state}",
                "lease": record.to_dict(),
            }
        expected_lease_id = record.lease_id
        expected_generation = record.generation
        expected_fingerprint = record.to_sidecar_dict()["token_fingerprint"]

    is_path_key = os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd")
    if is_path_key and (
        sidecar_error := _validate_save_sidecar(
            doc_key,
            expected_lease_id=expected_lease_id,
            expected_generation=expected_generation,
            expected_fingerprint=expected_fingerprint,
        )
    ):
        return sidecar_error

    with _registry_lock:
        record = _registry.get(doc_key)
        if (
            record is None
            or record.lease_id != expected_lease_id
            or record.generation != expected_generation
            or not hmac.compare_digest(str(record.token), str(token))
        ):
            return {
                "success": False,
                "error_code": "lease_replaced",
                "error": "The compatibility lease changed before save promotion",
            }
        record.state = LeaseState.LOCKED_IDLE.value
        record.state_revision += 1
        record.record_revision += 1
        record.last_heartbeat = current_time()
        record.current_operation = ""
        record.document_dirty = False
        record.last_save_time = current_time()
        record.baseline_mtime = float(baseline_mtime)
        record.baseline_hash = str(baseline_hash)
        record.last_verified_save_revision = record.last_mutation_revision
        record.error_info = None
        payload = record.to_dict()
        sidecar_payload = record.to_sidecar_dict()

    if is_path_key:
        try:
            _write_json_atomic(sidecar_path_for(doc_key), sidecar_payload)
        except OSError as exc:
            with _registry_lock:
                current = _registry.get(doc_key)
                if current is not None:
                    current.state = LeaseState.LOCKED_ERROR.value
                    current.error_info = {
                        "code": "sidecar_write_failed",
                        "message": str(exc),
                    }
            return {
                "success": False,
                "error_code": "sidecar_write_failed",
                "error": str(exc),
                "lease": payload,
            }
    return {"success": True, "lease": payload}
