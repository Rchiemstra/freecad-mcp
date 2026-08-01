from __future__ import annotations

import hmac
import os
from typing import Any

from .lease_state import LeaseState
from .registry_state import _registry, _registry_lock
from .sidecar_io import _read_sidecar, sidecar_path_for


def release_lease(doc_key: str, token: str) -> dict[str, Any]:
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
        if record.state != LeaseState.LOCKED_IDLE.value:
            return {
                "success": False,
                "error_code": "lease_not_releasable",
                "error": f"Cannot cleanly release a lease in {record.state}",
                "lease": record.to_dict(),
            }
        if record.document_dirty:
            return {
                "success": False,
                "error_code": "document_dirty",
                "error": "Dirty documents must be saved/verified or restored before release",
                "lease": record.to_dict(),
            }
        if record.last_verified_save_revision < record.last_mutation_revision:
            return {
                "success": False,
                "error_code": "save_not_verified",
                "error": "The verified save predates the last mutation",
                "lease": record.to_dict(),
            }
        record.state = LeaseState.RELEASING.value
        record.state_revision += 1
        record.record_revision += 1

    is_path_key = os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd")
    if is_path_key:
        side = sidecar_path_for(doc_key)
        persisted = _read_sidecar(side)
        if not persisted:
            with _registry_lock:
                record.state = LeaseState.LOCKED_ERROR.value
                record.error_info = {
                    "code": "sidecar_missing",
                    "message": "Sidecar disappeared during release",
                }
            return {
                "success": False,
                "error_code": "sidecar_missing",
                "error": "Sidecar disappeared during release; ownership remains fenced",
                "lease": record.to_dict(),
            }
        if (
            persisted.get("lease_id") != record.lease_id
            or int(persisted.get("generation", 0)) != record.generation
            or not hmac.compare_digest(
                str(persisted.get("token_fingerprint", "")),
                str(record.to_sidecar_dict()["token_fingerprint"]),
            )
        ):
            with _registry_lock:
                record.state = LeaseState.LOCKED_ERROR.value
                record.error_info = {
                    "code": "sidecar_replaced",
                    "message": "Sidecar ownership changed during release",
                }
            return {
                "success": False,
                "error_code": "sidecar_replaced",
                "error": "Sidecar ownership changed during release",
                "lease": record.to_dict(),
            }
        try:
            side.unlink()
        except OSError as exc:
            with _registry_lock:
                record.state = LeaseState.LOCKED_ERROR.value
                record.error_info = {
                    "code": "sidecar_remove_failed",
                    "message": str(exc),
                }
            return {
                "success": False,
                "error_code": "sidecar_remove_failed",
                "error": str(exc),
                "lease": record.to_dict(),
            }
    with _registry_lock:
        _registry.pop(doc_key, None)
    return {
        "success": True,
        "released": doc_key,
        "terminal_state": LeaseState.UNLOCKED_SAVED.value,
    }
