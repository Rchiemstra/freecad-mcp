from __future__ import annotations

import hmac
import os
from typing import Any

from .facade_surfaces import current_time
from .registry_state import _registry, _registry_lock
from .sidecar_io import _write_json_atomic, sidecar_path_for


def heartbeat_lease(
    doc_key: str,
    token: str,
    *,
    current_operation: str | None = None,
    state: str | None = None,
    document_dirty: bool | None = None,
) -> dict[str, Any]:
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
        record.last_heartbeat = current_time()
        if current_operation is not None:
            record.current_operation = current_operation
        if state is not None and state != record.state:
            return {
                "success": False,
                "error_code": "state_owned_by_server",
                "error": "Heartbeat cannot change the lease state",
                "lease": record.to_dict(),
            }
        if document_dirty is not None and bool(document_dirty) != record.document_dirty:
            return {
                "success": False,
                "error_code": "dirty_state_owned_by_server",
                "error": "Heartbeat cannot change authoritative document dirty state",
                "lease": record.to_dict(),
            }
        record.heartbeat_sequence += 1
        record.record_revision += 1
        payload = record.to_dict()
        sidecar_payload = record.to_sidecar_dict()

    is_path_key = os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd")
    if is_path_key:
        side = sidecar_path_for(doc_key)
        if side.is_file():
            _write_json_atomic(side, sidecar_payload)
    return {"success": True, "lease": payload}
