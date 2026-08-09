from __future__ import annotations

import hmac
import os
import uuid
from pathlib import Path
from typing import Any

from . import settings as _settings_module
from .agent_mutation_ops import _agent_mutation_ctx
from .constants import LEASE_TTL_SECONDS
from .eligibility import _is_eligible_target
from .internal_snapshot_save_ops import _internal_snapshot_save_ctx
from .lease_record import LeaseRecord
from .module_aliases import install_module_aliases
from .registry_state import (
    _pending_saves,
    _registry,
    _registry_lock,
    _session_ids,
)
from .request_identity import clear_request_identity
from .sidecar_io import _read_sidecar, sidecar_path_for


def reset_registry_for_tests() -> None:
    """Clear in-memory state (unit tests only)."""
    with _registry_lock:
        _registry.clear()
        _session_ids.clear()
        _pending_saves.clear()
    _settings_module._runtime_lease_mode = None
    if hasattr(_agent_mutation_ctx, "state"):
        delattr(_agent_mutation_ctx, "state")
    if hasattr(_internal_snapshot_save_ctx, "state"):
        delattr(_internal_snapshot_save_ctx, "state")
    clear_request_identity()


def get_session_id_for_name(doc_name: str) -> str | None:
    with _registry_lock:
        return _session_ids.get(doc_name)


def ensure_session_id(doc_name: str) -> str:
    with _registry_lock:
        existing = _session_ids.get(doc_name)
        if existing:
            return existing
        new_id = str(uuid.uuid4())
        _session_ids[doc_name] = new_id
        return new_id


def resolve_doc_key(
    *,
    doc_name: str | None = None,
    file_path: str | None = None,
    session_id: str | None = None,
) -> str:
    """Resolve canonical lock key: absolute path for saved docs, else session UUID."""
    if session_id:
        return session_id
    if file_path:
        return str(Path(file_path).resolve())
    if doc_name:
        try:
            import FreeCAD

            doc = FreeCAD.getDocument(doc_name)
            if doc is not None:
                fname = getattr(doc, "FileName", None) or ""
                if fname and _is_eligible_target(fname):
                    return str(Path(fname).resolve())
                return ensure_session_id(doc_name)
        except ImportError:
            pass
        return ensure_session_id(doc_name)
    raise ValueError("document identity required (doc_name, file_path, or session_id)")


def _is_stale(record: LeaseRecord, *, now: float | None = None) -> bool:
    from .facade_surfaces import current_time

    resolved = current_time() if now is None else now
    return (resolved - float(record.last_heartbeat)) > LEASE_TTL_SECONDS


def get_lease(doc_key: str) -> LeaseRecord | None:
    with _registry_lock:
        return _registry.get(doc_key)


def list_leases() -> list[LeaseRecord]:
    with _registry_lock:
        return list(_registry.values())


def inspect_persisted_compatibility_lease(doc_key: str) -> dict[str, Any] | None:
    """Return a redacted live v1 lease only when its sidecar still matches."""
    if not (os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd")):
        return None
    with _registry_lock:
        record = _registry.get(doc_key)
    if record is None:
        return None
    persisted = _read_sidecar(sidecar_path_for(doc_key))
    if not persisted:
        return None
    if "schema_version" in persisted or "record_kind" in persisted:
        return None
    try:
        generation_matches = int(persisted.get("generation", 0)) == int(
            record.generation
        )
    except (TypeError, ValueError):
        generation_matches = False
    expected_fingerprint = record.to_sidecar_dict()["token_fingerprint"]
    if (
        persisted.get("doc_key") != record.doc_key
        or persisted.get("lease_id") != record.lease_id
        or not generation_matches
        or not hmac.compare_digest(
            str(persisted.get("token_fingerprint", "")),
            str(expected_fingerprint),
        )
    ):
        return None
    return record.to_dict()


def discover_sidecar_leases(search_paths: list[str] | None = None) -> list[LeaseRecord]:
    """Load leases from known sidecars next to provided FCStd paths."""
    found: list[LeaseRecord] = []
    for raw in search_paths or []:
        if not raw or not _is_eligible_target(raw):
            continue
        side = sidecar_path_for(str(Path(raw).resolve()))
        data = _read_sidecar(side)
        if data:
            try:
                found.append(LeaseRecord.from_dict(data))
            except TypeError:
                continue
    return found


install_module_aliases(__name__)
