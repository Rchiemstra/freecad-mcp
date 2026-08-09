from __future__ import annotations

import hmac
import os
from typing import Any

from .facade_surfaces import current_time
from .lease_state import LeaseState
from .registry_state import _registry, _registry_lock
from .sidecar_io import _write_json_atomic, sidecar_path_for

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    LeaseState.ACQUIRING.value: {
        LeaseState.LOCKED_IDLE.value,
        LeaseState.LOCKED_ERROR.value,
    },
    LeaseState.LOCKED_IDLE.value: {
        LeaseState.LOCKED_EDITING.value,
        LeaseState.LOCKED_RECOMPUTING.value,
        LeaseState.LOCKED_SAVING.value,
        LeaseState.LOCKED_ERROR.value,
        LeaseState.USER_INTERVENED.value,
        LeaseState.CANCELLING.value,
        LeaseState.RELEASING.value,
        LeaseState.STALE.value,
    },
    LeaseState.LOCKED_EDITING.value: {
        LeaseState.LOCKED_IDLE.value,
        LeaseState.LOCKED_RECOMPUTING.value,
        LeaseState.LOCKED_ERROR.value,
        LeaseState.USER_INTERVENED.value,
        LeaseState.CANCELLING.value,
        LeaseState.STALE.value,
    },
    LeaseState.LOCKED_RECOMPUTING.value: {
        LeaseState.LOCKED_IDLE.value,
        LeaseState.LOCKED_ERROR.value,
        LeaseState.USER_INTERVENED.value,
        LeaseState.CANCELLING.value,
        LeaseState.STALE.value,
    },
    LeaseState.LOCKED_SAVING.value: {
        LeaseState.LOCKED_IDLE.value,
        LeaseState.LOCKED_ERROR.value,
        LeaseState.USER_INTERVENED.value,
        LeaseState.STALE.value,
    },
    LeaseState.LOCKED_ERROR.value: {
        LeaseState.LOCKED_EDITING.value,
        LeaseState.LOCKED_SAVING.value,
        LeaseState.USER_INTERVENED.value,
        LeaseState.CANCELLING.value,
        LeaseState.UNLOCKED_DIRTY.value,
        LeaseState.STALE.value,
    },
    LeaseState.CANCELLING.value: {
        LeaseState.LOCKED_IDLE.value,
        LeaseState.LOCKED_ERROR.value,
        LeaseState.USER_INTERVENED.value,
    },
    LeaseState.RELEASING.value: {
        LeaseState.UNLOCKED_SAVED.value,
        LeaseState.LOCKED_ERROR.value,
    },
    LeaseState.STALE.value: {
        LeaseState.LOCKED_IDLE.value,
        LeaseState.USER_INTERVENED.value,
        LeaseState.UNLOCKED_DIRTY.value,
    },
    LeaseState.USER_INTERVENED.value: {LeaseState.UNLOCKED_DIRTY.value},
    LeaseState.UNLOCKED_DIRTY.value: {LeaseState.ACQUIRING.value},
    LeaseState.UNLOCKED_SAVED.value: {LeaseState.ACQUIRING.value},
}


def _transition_validation_error(
    doc_key: str,
    token: str,
    new_state: str,
) -> dict[str, Any] | None:
    if new_state not in {state.value for state in LeaseState}:
        return {
            "success": False,
            "error_code": "invalid_lease_state",
            "error": f"Unknown lease state: {new_state}",
        }
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
        if new_state != record.state and new_state not in _ALLOWED_TRANSITIONS.get(
            record.state, set()
        ):
            return {
                "success": False,
                "error_code": "forbidden_lease_transition",
                "error": f"Transition {record.state} -> {new_state} is forbidden",
                "lease": record.to_dict(),
            }
    return None


def _commit_transition(
    doc_key: str,
    *,
    new_state: str,
    current_operation: str | None,
    document_dirty: bool | None,
    request_id: str | None,
    error: dict[str, Any] | None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    with _registry_lock:
        record = _registry[doc_key]
        previous = record.state
        record.state = new_state
        record.state_revision += 1
        record.record_revision += 1
        record.last_heartbeat = current_time()
        record.request_id = request_id
        if current_operation is not None:
            record.current_operation = current_operation
        if document_dirty is not None:
            dirty = bool(document_dirty)
            if dirty and not record.document_dirty:
                record.last_mutation_revision += 1
            record.document_dirty = dirty
        record.error_info = error
        if new_state == LeaseState.USER_INTERVENED.value:
            record.user_intervened = True
        payload = record.to_dict()
        sidecar_payload = record.to_sidecar_dict()
    return previous, payload, sidecar_payload


def transition_lease(
    doc_key: str,
    token: str,
    new_state: str,
    *,
    current_operation: str | None = None,
    document_dirty: bool | None = None,
    request_id: str | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Commit a server-owned state transition and persist it immediately."""
    if validation_error := _transition_validation_error(doc_key, token, new_state):
        return validation_error
    previous, payload, sidecar_payload = _commit_transition(
        doc_key,
        new_state=new_state,
        current_operation=current_operation,
        document_dirty=document_dirty,
        request_id=request_id,
        error=error,
    )

    if os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd"):
        side = sidecar_path_for(doc_key)
        if not side.is_file():
            return {
                "success": False,
                "error_code": "sidecar_missing",
                "error": "Saved-document sidecar is missing; writes remain blocked",
                "lease": payload,
            }
        try:
            _write_json_atomic(side, sidecar_payload)
        except OSError as exc:
            with _registry_lock:
                if doc_key in _registry:
                    _registry[doc_key].state = LeaseState.LOCKED_ERROR.value
                    _registry[doc_key].error_info = {
                        "code": "sidecar_write_failed",
                        "message": str(exc),
                    }
            return {
                "success": False,
                "error_code": "sidecar_write_failed",
                "error": str(exc),
                "lease": payload,
            }
    return {
        "success": True,
        "previous_state": previous,
        "lease": payload,
    }
