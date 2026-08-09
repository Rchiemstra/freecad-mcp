from __future__ import annotations

import os
import secrets
import uuid
from typing import Any

from .eligibility import _is_eligible_target
from .facade_surfaces import current_time
from .file_baseline import file_baseline
from .lease_record import LeaseRecord
from .lease_state import LeaseState
from .registry_queries import _is_stale, ensure_session_id
from .registry_state import _registry, _registry_lock, _session_ids
from .sidecar_io import (
    _create_sidecar_exclusive,
    _public_sidecar_payload,
    _read_sidecar,
    _write_json_atomic,
    sidecar_path_for,
)


def _acquire_target_error(doc_key: str) -> dict[str, Any] | None:
    is_path_key = os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd")
    if not is_path_key:
        return None
    if _is_eligible_target(doc_key):
        return None
    return {
        "success": False,
        "error_code": "ineligible_target",
        "error": f"Document path is not eligible for locking: {doc_key}",
    }


def _renew_existing_lease(
    existing: LeaseRecord,
    *,
    token: str,
    now: float,
    client: str,
    pid: int,
    host: str,
    task_description: str,
    document_dirty: bool,
    doc_key: str,
    is_path_key: bool,
) -> dict[str, Any]:
    if existing.state in {
        LeaseState.USER_INTERVENED.value,
        LeaseState.UNLOCKED_DIRTY.value,
        LeaseState.STALE.value,
    }:
        return {
            "success": False,
            "error_code": "local_recovery_required",
            "error": (
                f"Lease is in {existing.state}; the previous agent may "
                "not automatically reacquire it"
            ),
            "lease": existing.to_dict(),
        }
    existing.token = token
    existing.token_fingerprint = ""
    existing.last_heartbeat = now
    existing.client = client or existing.client
    existing.pid = int(pid or existing.pid)
    existing.host = host or existing.host
    if task_description:
        existing.task_description = task_description
    existing.document_dirty = bool(document_dirty)
    payload = existing.to_dict()
    sidecar_payload = existing.to_sidecar_dict()
    if is_path_key:
        side = sidecar_path_for(doc_key)
        if side.is_file():
            _write_json_atomic(side, sidecar_payload)
        else:
            _create_sidecar_exclusive(side, sidecar_payload)
    return {"success": True, "token": token, "lease": payload, "renewed": True}


def _sidecar_acquire_conflict(
    doc_key: str,
    *,
    instance_id: str,
    now: float,
) -> dict[str, Any] | None:
    side = sidecar_path_for(doc_key)
    existing_side = _read_sidecar(side)
    if not existing_side:
        return None
    try:
        side_rec = LeaseRecord.from_dict(existing_side)
    except TypeError:
        side_rec = None
    if (
        side_rec
        and not _is_stale(side_rec, now=now)
        and side_rec.instance_id != instance_id
    ):
        return {
            "success": False,
            "error_code": "document_locked_by_other",
            "error": (
                f"Sidecar lock held by instance {side_rec.instance_id} "
                f"(pid={side_rec.pid})"
            ),
            "lease": side_rec.to_dict(),
        }
    if side_rec is None or _is_stale(side_rec, now=now):
        return {
            "success": False,
            "error_code": "stale_lock_recovery_required",
            "error": (
                "A stale or unknown sidecar remains authoritative until "
                "a confirmed local recovery action resolves it"
            ),
            "lease": side_rec.to_dict() if side_rec else None,
        }
    return None


def acquire_lease(
    *,
    doc_key: str,
    doc_name: str,
    instance_id: str,
    client: str = "",
    pid: int = 0,
    host: str = "",
    task_description: str = "",
    rpc_port: int | None = None,
    document_dirty: bool = False,
) -> dict[str, Any]:
    """Acquire a legacy v1 lease for migration tests and existing adapters."""
    if not instance_id:
        return {
            "success": False,
            "error_code": "missing_instance_id",
            "error": "instance_id is required to acquire a document lock",
        }

    is_path_key = os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd")
    if target_error := _acquire_target_error(doc_key):
        return target_error

    baseline_mtime = baseline_hash = None
    if is_path_key:
        baseline_mtime, baseline_hash = file_baseline(doc_key)

    token = secrets.token_urlsafe(32)
    now = current_time()
    record = LeaseRecord(
        doc_key=doc_key,
        doc_name=doc_name,
        token=token,
        instance_id=instance_id,
        client=client or "",
        pid=int(pid or 0),
        host=host or "",
        task_description=task_description or "",
        acquired_at=now,
        last_heartbeat=now,
        current_operation="",
        document_dirty=bool(document_dirty),
        baseline_mtime=baseline_mtime,
        baseline_hash=baseline_hash,
        state=LeaseState.LOCKED_IDLE.value,
        rpc_port=rpc_port,
        document_session_uuid=(
            ensure_session_id(doc_name) if doc_name else str(uuid.uuid4())
        ),
    )

    with _registry_lock:
        existing = _registry.get(doc_key)
        if existing and not _is_stale(existing, now=now):
            if existing.instance_id == instance_id:
                return _renew_existing_lease(
                    existing,
                    token=token,
                    now=now,
                    client=client,
                    pid=pid,
                    host=host,
                    task_description=task_description,
                    document_dirty=document_dirty,
                    doc_key=doc_key,
                    is_path_key=is_path_key,
                )
            return {
                "success": False,
                "error_code": "document_locked_by_other",
                "error": (
                    f"Document is locked by instance {existing.instance_id} "
                    f"(pid={existing.pid}, client={existing.client!r})"
                ),
                "lease": existing.to_dict(),
            }

        if is_path_key:
            if conflict := _sidecar_acquire_conflict(
                doc_key, instance_id=instance_id, now=now
            ):
                return conflict
            side = sidecar_path_for(doc_key)
            if not _create_sidecar_exclusive(side, record.to_sidecar_dict()):
                raced = _read_sidecar(side)
                return {
                    "success": False,
                    "error_code": "document_locked_by_other",
                    "error": "Failed to create exclusive sidecar (lost race)",
                    "lease": _public_sidecar_payload(raced),
                }

        _registry[doc_key] = record
        if doc_name and not is_path_key:
            _session_ids[doc_name] = doc_key

    return {"success": True, "token": token, "lease": record.to_dict()}
