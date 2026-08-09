from __future__ import annotations

import os
import secrets

from .lease_record import LeaseRecord
from .lease_state import LeaseState
from .registry_state import _registry, _registry_lock
from .sidecar_io import _write_json_atomic, sidecar_path_for


def mark_user_intervened(doc_key: str) -> LeaseRecord | None:
    with _registry_lock:
        record = _registry.get(doc_key)
        if record is None:
            return None
        record.state = LeaseState.USER_INTERVENED.value
        record.generation += 1
        record.token = secrets.token_urlsafe(32)
        record.token_fingerprint = ""
        record.state_revision += 1
        record.record_revision += 1
        record.user_intervened = True
        record.current_operation = "user_intervened"
        sidecar_payload = record.to_sidecar_dict()
    if os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd"):
        side = sidecar_path_for(doc_key)
        if side.is_file():
            _write_json_atomic(side, sidecar_payload)
    return record
