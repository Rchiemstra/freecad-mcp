"""Per-document renewable write lease for MCP agents.

Pure/unit-testable core: lease registry, atomic sidecar lock files, staleness
checks, and Save As / first-save key migration. FreeCAD and Qt are imported
lazily so the module loads under the stubbed unit harness.

When ``enable_document_lock`` is false (default), nothing is registered, no
sidecars are written, and callers should treat this module as inert.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def _settings_path() -> Path:
    try:
        import FreeCAD

        return Path(FreeCAD.getUserAppDataDir()) / "freecad_mcp_settings.json"
    except ImportError:
        return Path.home() / "freecad_mcp_settings.json"


def _read_settings() -> dict[str, Any]:
    path = _settings_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def is_enabled() -> bool:
    """True when document lock infrastructure (observer/GUI/sidecars) is on."""
    return bool(_read_settings().get("enable_document_lock", False))


def is_enforcement_enabled() -> bool:
    """True when mutating RPC verbs must present a valid owned lease."""
    data = _read_settings()
    return bool(data.get("document_lock_enforcement", False)) and bool(
        data.get("enable_document_lock", False)
    )


# ---------------------------------------------------------------------------
# Eligibility (reuse git_sidecar rules for saved paths)
# ---------------------------------------------------------------------------

def _is_eligible_target(filename: str) -> bool:
    """Skip recovery/snapshot/backup paths — never lock those files."""
    try:
        from git_sidecar import _is_eligible_target as _git_eligible

        return _git_eligible(filename)
    except ImportError:
        path = Path(filename)
        name_lower = path.name.lower()
        if not name_lower.endswith(".fcstd"):
            return False
        for pattern in (".fcstd1", ".fcstd2", ".bak", ".tmp", ".recovery", "mcp_snap_", "~"):
            if pattern in name_lower:
                return False
        parts = {p.lower() for p in path.parts}
        if parts & {"fc_recovery_files", "recovery", "autosave", "snapshots", "snapshot"}:
            return False
        return True


# ---------------------------------------------------------------------------
# Lease model
# ---------------------------------------------------------------------------

LEASE_TTL_SECONDS = 90.0
SIDECAR_SUFFIX = ".freecad-mcp.lock"


class LeaseState(str, Enum):
    LOCKED_EDITING = "LOCKED_EDITING"
    LOCKED_RECOMPUTING = "LOCKED_RECOMPUTING"
    LOCKED_SAVING = "LOCKED_SAVING"
    LOCKED_ERROR = "LOCKED_ERROR"
    USER_INTERVENED = "USER_INTERVENED"
    UNLOCKED_SAVED = "UNLOCKED_SAVED"
    UNLOCKED_DIRTY = "UNLOCKED_DIRTY"


@dataclass
class LeaseRecord:
    doc_key: str
    doc_name: str
    token: str
    instance_id: str
    client: str
    pid: int
    host: str
    task_description: str = ""
    acquired_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    current_operation: str = ""
    document_dirty: bool = False
    last_save_time: float | None = None
    baseline_mtime: float | None = None
    baseline_hash: str | None = None
    state: str = LeaseState.LOCKED_EDITING.value
    rpc_port: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LeaseRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# Thread-local request identity + agent-mutating flag
# ---------------------------------------------------------------------------

_request_ctx = threading.local()
_agent_mutating: set[str] = set()
_agent_mutating_lock = threading.Lock()


def set_request_identity(
    *,
    instance_id: str | None = None,
    client: str | None = None,
    pid: int | None = None,
    host: str | None = None,
    lease_token: str | None = None,
    rpc_port: int | None = None,
) -> None:
    _request_ctx.instance_id = instance_id
    _request_ctx.client = client
    _request_ctx.pid = pid
    _request_ctx.host = host
    _request_ctx.lease_token = lease_token
    _request_ctx.rpc_port = rpc_port


def clear_request_identity() -> None:
    for attr in ("instance_id", "client", "pid", "host", "lease_token", "rpc_port"):
        if hasattr(_request_ctx, attr):
            delattr(_request_ctx, attr)


def get_request_identity() -> dict[str, Any]:
    return {
        "instance_id": getattr(_request_ctx, "instance_id", None),
        "client": getattr(_request_ctx, "client", None),
        "pid": getattr(_request_ctx, "pid", None),
        "host": getattr(_request_ctx, "host", None),
        "lease_token": getattr(_request_ctx, "lease_token", None),
        "rpc_port": getattr(_request_ctx, "rpc_port", None),
    }


def begin_agent_mutation(doc_key: str) -> None:
    with _agent_mutating_lock:
        _agent_mutating.add(doc_key)


def end_agent_mutation(doc_key: str) -> None:
    with _agent_mutating_lock:
        _agent_mutating.discard(doc_key)


def is_agent_mutating(doc_key: str) -> bool:
    with _agent_mutating_lock:
        return doc_key in _agent_mutating


# ---------------------------------------------------------------------------
# Sidecar helpers
# ---------------------------------------------------------------------------

def sidecar_path_for(file_path: str) -> Path:
    return Path(f"{file_path}{SIDECAR_SUFFIX}")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Same idiom as worker_protocol.write_json_atomic (no size cap)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.remove(tmp_name)
        except OSError:
            pass
        raise


def _create_sidecar_exclusive(path: Path, payload: dict[str, Any]) -> bool:
    """Atomically create a sidecar. Returns False if it already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(path), flags)
    except FileExistsError:
        return False
    except OSError as exc:
        # Windows may raise EEXIST-equivalent
        if getattr(exc, "errno", None) in (getattr(os, "EEXIST", 17), 17):
            return False
        raise
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        os.write(fd, encoded)
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


def _read_sidecar(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _remove_sidecar(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except TypeError:
        # Python < 3.8 compatibility (FreeCAD may ship older)
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass
    except OSError:
        pass


def file_baseline(file_path: str) -> tuple[float | None, str | None]:
    """Return (mtime, sha256 hex) for an on-disk FCStd, or (None, None)."""
    path = Path(file_path)
    if not path.is_file():
        return None, None
    try:
        st = path.stat()
        mtime = float(st.st_mtime)
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return mtime, h.hexdigest()
    except OSError:
        return None, None


def verify_saved_file(file_path: str, *, expect_hash: str | None = None) -> dict[str, Any]:
    path = Path(file_path)
    if not path.is_file():
        return {"ok": False, "error": "file_missing", "path": file_path}
    mtime, digest = file_baseline(file_path)
    if expect_hash is not None and digest != expect_hash:
        return {
            "ok": False,
            "error": "hash_mismatch",
            "path": file_path,
            "expected": expect_hash,
            "actual": digest,
        }
    return {"ok": True, "path": file_path, "mtime": mtime, "hash": digest}


def pid_alive(pid: int) -> bool:
    """Best-effort liveness check (POSIX kill(0) / Windows OpenProcess)."""
    if pid is None or int(pid) <= 0:
        return False
    pid = int(pid)
    if sys.platform == "win32":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_registry: dict[str, LeaseRecord] = {}
_registry_lock = threading.Lock()
# Document.Name → session UUID for unsaved docs
_session_ids: dict[str, str] = {}
# Pending Save As migrations: doc_name → destination path being written
_pending_saves: dict[str, str] = {}


def reset_registry_for_tests() -> None:
    """Clear in-memory state (unit tests only)."""
    with _registry_lock:
        _registry.clear()
        _session_ids.clear()
        _pending_saves.clear()
    with _agent_mutating_lock:
        _agent_mutating.clear()
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
        # Prefer live FreeCAD document FileName when available
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
    now = time.time() if now is None else now
    return (now - float(record.last_heartbeat)) > LEASE_TTL_SECONDS


def get_lease(doc_key: str) -> LeaseRecord | None:
    with _registry_lock:
        return _registry.get(doc_key)


def list_leases() -> list[LeaseRecord]:
    with _registry_lock:
        return list(_registry.values())


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
    """Acquire an exclusive lease. Creates sidecar for path-keyed (saved) docs."""
    if not instance_id:
        return {
            "success": False,
            "error_code": "missing_instance_id",
            "error": "instance_id is required to acquire a document lock",
        }

    # Path keys are absolute filesystem paths; session keys are UUIDs.
    is_path_key = os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd")

    baseline_mtime = baseline_hash = None
    if is_path_key:
        if not _is_eligible_target(doc_key):
            return {
                "success": False,
                "error_code": "ineligible_target",
                "error": f"Document path is not eligible for locking: {doc_key}",
            }
        baseline_mtime, baseline_hash = file_baseline(doc_key)

    token = uuid.uuid4().hex
    now = time.time()
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
        state=LeaseState.LOCKED_EDITING.value,
        rpc_port=rpc_port,
    )

    with _registry_lock:
        existing = _registry.get(doc_key)
        if existing and not _is_stale(existing, now=now):
            if existing.instance_id == instance_id:
                # Same instance re-acquires: refresh token + heartbeat in place
                existing.token = token
                existing.last_heartbeat = now
                existing.client = client or existing.client
                existing.pid = int(pid or existing.pid)
                existing.host = host or existing.host
                if task_description:
                    existing.task_description = task_description
                existing.document_dirty = bool(document_dirty)
                payload = existing.to_dict()
                if is_path_key:
                    side = sidecar_path_for(doc_key)
                    if side.is_file():
                        _write_json_atomic(side, payload)
                    else:
                        _create_sidecar_exclusive(side, payload)
                return {"success": True, "token": token, "lease": payload, "renewed": True}
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
            side = sidecar_path_for(doc_key)
            existing_side = _read_sidecar(side)
            if existing_side:
                try:
                    side_rec = LeaseRecord.from_dict(existing_side)
                except TypeError:
                    side_rec = None
                if side_rec and not _is_stale(side_rec, now=now):
                    if side_rec.instance_id != instance_id:
                        return {
                            "success": False,
                            "error_code": "document_locked_by_other",
                            "error": (
                                f"Sidecar lock held by instance {side_rec.instance_id} "
                                f"(pid={side_rec.pid})"
                            ),
                            "lease": side_rec.to_dict(),
                        }
                # Stale sidecar: remove before exclusive create
                if side_rec is None or _is_stale(side_rec, now=now):
                    # Only auto-clear if owner pid is dead (or unknown)
                    if side_rec is None or not pid_alive(side_rec.pid):
                        _remove_sidecar(side)
                    else:
                        return {
                            "success": False,
                            "error_code": "document_locked_by_other",
                            "error": (
                                "Sidecar lock heartbeat expired but owning pid "
                                f"{side_rec.pid} is still alive; use force_release_stale_lock "
                                "only after confirming the owner is gone"
                            ),
                            "lease": side_rec.to_dict(),
                        }

            if not _create_sidecar_exclusive(side, record.to_dict()):
                # Race: another process created it first
                raced = _read_sidecar(side)
                return {
                    "success": False,
                    "error_code": "document_locked_by_other",
                    "error": "Failed to create exclusive sidecar (lost race)",
                    "lease": raced,
                }

        _registry[doc_key] = record
        if doc_name:
            # Keep session map if this is a UUID key
            if not is_path_key:
                _session_ids[doc_name] = doc_key

    return {"success": True, "token": token, "lease": record.to_dict()}


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
        if record.token != token:
            return {
                "success": False,
                "error_code": "invalid_lease_token",
                "error": "Lease token does not match",
                "lease": record.to_dict(),
            }
        record.last_heartbeat = time.time()
        if current_operation is not None:
            record.current_operation = current_operation
        if state is not None:
            record.state = state
        if document_dirty is not None:
            record.document_dirty = bool(document_dirty)
        payload = record.to_dict()

    is_path_key = os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd")
    if is_path_key:
        side = sidecar_path_for(doc_key)
        if side.is_file():
            _write_json_atomic(side, payload)
    return {"success": True, "lease": payload}


def release_lease(doc_key: str, token: str) -> dict[str, Any]:
    with _registry_lock:
        record = _registry.get(doc_key)
        if record is None:
            return {
                "success": False,
                "error_code": "document_not_locked",
                "error": "No active lease for this document",
            }
        if record.token != token:
            return {
                "success": False,
                "error_code": "invalid_lease_token",
                "error": "Lease token does not match",
                "lease": record.to_dict(),
            }
        del _registry[doc_key]

    is_path_key = os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd")
    if is_path_key:
        _remove_sidecar(sidecar_path_for(doc_key))
    return {"success": True, "released": doc_key}


def force_release_stale_lock(doc_key: str) -> dict[str, Any]:
    """Remove a stale lock only after verifying the owning pid is dead."""
    now = time.time()
    side = None
    record: LeaseRecord | None = None

    with _registry_lock:
        record = _registry.get(doc_key)

    is_path_key = os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd")
    if is_path_key:
        side = sidecar_path_for(doc_key)
        side_data = _read_sidecar(side)
        if side_data:
            try:
                record = LeaseRecord.from_dict(side_data)
            except TypeError:
                pass

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

    if pid_alive(record.pid):
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
        # Create destination sidecar first (no unlocked interval)
        migrated = LeaseRecord(
            **{
                **record.to_dict(),
                "doc_key": new_key,
                "doc_name": doc_name or record.doc_name,
                "state": LeaseState.LOCKED_SAVING.value,
                "last_heartbeat": time.time(),
            }
        )
        mtime, digest = file_baseline(new_key)
        migrated.baseline_mtime = mtime
        migrated.baseline_hash = digest
        migrated.last_save_time = time.time()
        migrated.state = LeaseState.LOCKED_EDITING.value

        side_new = sidecar_path_for(new_key)
        if side_new.is_file():
            existing = _read_sidecar(side_new)
            if existing and existing.get("token") != record.token:
                other = LeaseRecord.from_dict(existing) if existing else None
                if other and not _is_stale(other) and pid_alive(other.pid):
                    return {
                        "success": False,
                        "error_code": "document_locked_by_other",
                        "error": "Destination path already locked by another instance",
                        "lease": other.to_dict(),
                    }
                if other is None or not pid_alive(other.pid):
                    _remove_sidecar(side_new)

        if not _create_sidecar_exclusive(side_new, migrated.to_dict()):
            # If we own a pre-created destination (Save As held it), overwrite
            existing = _read_sidecar(side_new)
            if existing and existing.get("token") == record.token:
                _write_json_atomic(side_new, migrated.to_dict())
            else:
                return {
                    "success": False,
                    "error_code": "document_locked_by_other",
                    "error": "Could not create destination sidecar",
                    "lease": existing,
                }

        _registry[new_key] = migrated
        _registry.pop(old_key, None)
        if doc_name:
            # Session id no longer primary key
            _session_ids.pop(doc_name, None)

    # Remove old sidecar only after new lease is valid
    if os.path.isabs(old_key) and old_key.lower().endswith(".fcstd"):
        _remove_sidecar(sidecar_path_for(old_key))

    return {"success": True, "lease": migrated.to_dict(), "old_key": old_key, "new_key": new_key}


def mark_user_intervened(doc_key: str) -> LeaseRecord | None:
    with _registry_lock:
        record = _registry.get(doc_key)
        if record is None:
            return None
        record.state = LeaseState.USER_INTERVENED.value
        record.current_operation = "user_intervened"
        payload = record.to_dict()
    if os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd"):
        side = sidecar_path_for(doc_key)
        if side.is_file():
            _write_json_atomic(side, payload)
    return record


def check_mutation_allowed(doc_key: str) -> dict[str, Any]:
    """Enforce ownership for a mutation on doc_key using request identity/token."""
    identity = get_request_identity()
    instance_id = identity.get("instance_id")
    token = identity.get("lease_token")

    with _registry_lock:
        record = _registry.get(doc_key)

    if record is None and os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd"):
        side = _read_sidecar(sidecar_path_for(doc_key))
        if side:
            try:
                record = LeaseRecord.from_dict(side)
            except TypeError:
                record = None

    if record is None:
        return {
            "success": False,
            "error_code": "document_not_locked",
            "error": (
                "No document lock held for this document. Call acquire_document_lock "
                "with an explicit document identity before mutating."
            ),
        }

    if record.state == LeaseState.USER_INTERVENED.value:
        return {
            "success": False,
            "error_code": "user_intervened",
            "error": (
                "A user edited this document while the agent held the lease. "
                "Stop and re-acquire deliberately after coordinating with the user."
            ),
            "lease": record.to_dict(),
        }

    if not instance_id or record.instance_id != instance_id:
        return {
            "success": False,
            "error_code": "document_locked_by_other",
            "error": (
                f"Document is locked by instance {record.instance_id} "
                f"(client={record.client!r}, pid={record.pid})"
            ),
            "lease": record.to_dict(),
        }

    if token and token != record.token:
        return {
            "success": False,
            "error_code": "invalid_lease_token",
            "error": "Presented lease token does not match the active lease",
            "lease": record.to_dict(),
        }

    return {"success": True, "lease": record.to_dict()}


def annotate_read_result(result: Any, doc_key: str | None) -> Any:
    """Attach lock ownership info to read-only results when another instance owns D."""
    if not doc_key:
        return result
    with _registry_lock:
        record = _registry.get(doc_key)
    if record is None and os.path.isabs(doc_key) and doc_key.lower().endswith(".fcstd"):
        side = _read_sidecar(sidecar_path_for(doc_key))
        if side:
            try:
                record = LeaseRecord.from_dict(side)
            except TypeError:
                record = None
    if record is None:
        return result
    identity = get_request_identity()
    owned_by_other = record.instance_id != identity.get("instance_id")
    annotation = {
        "document_lock": {
            "doc_key": record.doc_key,
            "state": record.state,
            "instance_id": record.instance_id,
            "client": record.client,
            "owned_by_caller": not owned_by_other,
            "owned_by_other": owned_by_other,
        }
    }
    if isinstance(result, dict):
        merged = dict(result)
        merged.update(annotation)
        return merged
    return {"result": result, **annotation}


# ---------------------------------------------------------------------------
# Verb classification (fail-closed)
# ---------------------------------------------------------------------------

class VerbKind(str, Enum):
    MUTATING = "MUTATING"
    READ_ONLY = "READ_ONLY"
    LIFECYCLE = "LIFECYCLE"


def _params0_doc(params: tuple) -> str | None:
    return params[0] if params else None


def _options_document(params: tuple) -> str | None:
    if len(params) < 2:
        return None
    options = params[1] if len(params) > 1 else None
    if isinstance(options, dict):
        return options.get("document")
    return None


def _none_doc(_params: tuple) -> str | None:
    return None


# Every public FreeCADRPC verb must appear here. Missing → treated as MUTATING.
VERB_CLASSIFICATION: dict[str, tuple[VerbKind, Callable[[tuple], str | None]]] = {
    # Lifecycle / control
    "ping": (VerbKind.LIFECYCLE, _none_doc),
    "get_instance_info": (VerbKind.LIFECYCLE, _none_doc),
    "check_rpc_sync": (VerbKind.LIFECYCLE, _none_doc),
    "get_worker_status": (VerbKind.LIFECYCLE, _none_doc),
    "cancel_worker_job": (VerbKind.LIFECYCLE, _none_doc),
    "shutdown_rpc_server": (VerbKind.LIFECYCLE, _none_doc),
    # Lock verbs themselves
    "acquire_document_lock": (VerbKind.LIFECYCLE, _none_doc),
    "get_document_lock": (VerbKind.LIFECYCLE, _none_doc),
    "list_document_locks": (VerbKind.LIFECYCLE, _none_doc),
    "heartbeat_document_lock": (VerbKind.LIFECYCLE, _none_doc),
    "release_document_lock": (VerbKind.LIFECYCLE, _none_doc),
    "force_release_stale_lock": (VerbKind.LIFECYCLE, _none_doc),
    # Document open/create (create needs no prior lease; open is read of file)
    "create_document": (VerbKind.MUTATING, _none_doc),  # no prior doc; gated specially
    "open_document": (VerbKind.READ_ONLY, _none_doc),
    "list_documents": (VerbKind.READ_ONLY, _none_doc),
    "activate_document": (VerbKind.READ_ONLY, _params0_doc),
    "reload_document": (VerbKind.MUTATING, _params0_doc),
    "close_document": (VerbKind.MUTATING, _params0_doc),
    # Mutating model ops
    "create_object": (VerbKind.MUTATING, _params0_doc),
    "edit_object": (VerbKind.MUTATING, _params0_doc),
    "delete_object": (VerbKind.MUTATING, _params0_doc),
    "repair_references": (VerbKind.MUTATING, _params0_doc),
    "insert_part_from_library": (VerbKind.MUTATING, _none_doc),
    "recompute_document": (VerbKind.MUTATING, _params0_doc),
    "recompute_and_wait": (VerbKind.MUTATING, _params0_doc),
    "undo": (VerbKind.MUTATING, _params0_doc),
    "redo": (VerbKind.MUTATING, _params0_doc),
    "restore": (VerbKind.MUTATING, _params0_doc),
    "snapshot": (VerbKind.READ_ONLY, _params0_doc),
    "run_fem_analysis": (VerbKind.MUTATING, _params0_doc),
    "solve_assembly": (VerbKind.MUTATING, _params0_doc),
    "sketch_create": (VerbKind.MUTATING, _params0_doc),
    "sketch_add_geometry": (VerbKind.MUTATING, _params0_doc),
    "sketch_add_constraint": (VerbKind.MUTATING, _params0_doc),
    "sketch_attach": (VerbKind.MUTATING, _params0_doc),
    "sketch_edit_constraint": (VerbKind.MUTATING, _params0_doc),
    "pad_feature": (VerbKind.MUTATING, _params0_doc),
    "pocket_feature": (VerbKind.MUTATING, _params0_doc),
    "spreadsheet_create": (VerbKind.MUTATING, _params0_doc),
    "spreadsheet_set_cells": (VerbKind.MUTATING, _params0_doc),
    "spreadsheet_set_alias": (VerbKind.MUTATING, _params0_doc),
    "set_expression": (VerbKind.MUTATING, _params0_doc),
    "clear_expression": (VerbKind.MUTATING, _params0_doc),
    "body_create": (VerbKind.MUTATING, _params0_doc),
    "body_set_tip": (VerbKind.MUTATING, _params0_doc),
    "animate_placement": (VerbKind.MUTATING, _params0_doc),
    "execute_code": (VerbKind.MUTATING, _options_document),
    "execute_code_async": (VerbKind.MUTATING, _none_doc),
    # Read-only
    "inspect_references": (VerbKind.READ_ONLY, _params0_doc),
    "get_objects": (VerbKind.READ_ONLY, _params0_doc),
    "get_object": (VerbKind.READ_ONLY, _params0_doc),
    "get_parts_list": (VerbKind.READ_ONLY, _none_doc),
    "get_active_screenshot": (VerbKind.READ_ONLY, _none_doc),
    "capture_view_sequence": (VerbKind.READ_ONLY, _none_doc),
    "capture_view_sequence_to_disk": (VerbKind.READ_ONLY, _none_doc),
    "refresh_view": (VerbKind.READ_ONLY, _none_doc),
    "get_selection": (VerbKind.READ_ONLY, _none_doc),
    "get_gui_state": (VerbKind.READ_ONLY, _none_doc),
    "set_tree_expanded": (VerbKind.READ_ONLY, _params0_doc),
    "select_subshapes": (VerbKind.READ_ONLY, _params0_doc),
    "set_section_view": (VerbKind.READ_ONLY, _none_doc),
    "get_recompute_log": (VerbKind.READ_ONLY, _params0_doc),
    "spreadsheet_get_cells": (VerbKind.READ_ONLY, _params0_doc),
    "spreadsheet_list_aliases": (VerbKind.READ_ONLY, _params0_doc),
    "list_expressions": (VerbKind.READ_ONLY, _params0_doc),
    "diagnose_parametric": (VerbKind.READ_ONLY, _params0_doc),
    "get_sketch_diagnostics": (VerbKind.READ_ONLY, _params0_doc),
}


def classify_verb(method: str) -> tuple[VerbKind, Callable[[tuple], str | None]]:
    """Fail-closed: unknown verbs are MUTATING with params[0] doc extractor."""
    if method in VERB_CLASSIFICATION:
        return VERB_CLASSIFICATION[method]
    return VerbKind.MUTATING, _params0_doc


def extract_referenced_documents_from_code(code: str) -> set[str]:
    """Best-effort AST scan for FreeCAD.getDocument('Name') string literals."""
    import ast

    names: set[str] = set()
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "getDocument":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(
                node.args[0].value, str
            ):
                names.add(node.args[0].value)
        if isinstance(func, ast.Name) and func.id == "getDocument":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(
                node.args[0].value, str
            ):
                names.add(node.args[0].value)
    return names


# ---------------------------------------------------------------------------
# Document observer (lazy FreeCAD)
# ---------------------------------------------------------------------------

_observer_registered = False
_gui_update_callback: Callable[[], None] | None = None


def set_gui_update_callback(callback: Callable[[], None] | None) -> None:
    global _gui_update_callback
    _gui_update_callback = callback


def _notify_gui() -> None:
    cb = _gui_update_callback
    if cb is not None:
        try:
            cb()
        except Exception:
            pass


def _doc_key_for_document(document) -> str | None:
    if document is None:
        return None
    name = getattr(document, "Name", None)
    fname = getattr(document, "FileName", None) or ""
    if fname and _is_eligible_target(fname):
        return str(Path(fname).resolve())
    if name:
        with _registry_lock:
            sid = _session_ids.get(name)
            if sid:
                return sid
            # Also match by doc_name on any lease
            for key, rec in _registry.items():
                if rec.doc_name == name:
                    return key
    return None


class DocumentLockObserver:
    """Detects user edits on locked docs and migrates leases on save."""

    def slotChangedObject(self, obj, prop):  # noqa: N802
        self._maybe_user_edit(getattr(obj, "Document", None))

    def slotCreatedObject(self, obj):  # noqa: N802
        self._maybe_user_edit(getattr(obj, "Document", None))

    def slotDeletedObject(self, obj):  # noqa: N802
        self._maybe_user_edit(getattr(obj, "Document", None))

    def slotStartSaveDocument(self, document, filename):  # noqa: N802
        if not is_enabled():
            return
        if not filename or not _is_eligible_target(filename):
            return
        dest = str(Path(filename).resolve())
        doc_name = getattr(document, "Name", "") or ""
        old_key = _doc_key_for_document(document)
        with _registry_lock:
            _pending_saves[doc_name] = dest
            record = _registry.get(old_key) if old_key else None
        if record is None:
            return
        # Pre-create destination sidecar with same token (no unlocked gap)
        side = sidecar_path_for(dest)
        if not side.is_file():
            pre = dict(record.to_dict())
            pre["doc_key"] = dest
            pre["state"] = LeaseState.LOCKED_SAVING.value
            pre["last_heartbeat"] = time.time()
            _create_sidecar_exclusive(side, pre)
        with _registry_lock:
            if old_key and old_key in _registry:
                _registry[old_key].state = LeaseState.LOCKED_SAVING.value
                _registry[old_key].current_operation = f"saving:{dest}"
        _notify_gui()

    def slotFinishSaveDocument(self, document, filename):  # noqa: N802
        if not is_enabled():
            return
        if not filename or not _is_eligible_target(filename):
            return
        dest = str(Path(filename).resolve())
        doc_name = getattr(document, "Name", "") or ""
        old_key = None
        with _registry_lock:
            _pending_saves.pop(doc_name, None)
            # Find lease by doc_name (may still be UUID or old path)
            for key, rec in list(_registry.items()):
                if rec.doc_name == doc_name or key == dest:
                    old_key = key
                    break
        if old_key is None:
            return
        verify = verify_saved_file(dest)
        if not verify.get("ok"):
            with _registry_lock:
                if old_key in _registry:
                    _registry[old_key].state = LeaseState.LOCKED_ERROR.value
            _notify_gui()
            return
        if old_key != dest:
            migrate_lease_key(old_key, dest, doc_name=doc_name)
        else:
            with _registry_lock:
                token = _registry[dest].token if dest in _registry else ""
            if token:
                heartbeat_lease(
                    dest,
                    token,
                    state=LeaseState.LOCKED_EDITING.value,
                    current_operation="",
                    document_dirty=False,
                )
        _notify_gui()

    def slotDeletedDocument(self, document):  # noqa: N802
        if not is_enabled():
            return
        key = _doc_key_for_document(document)
        name = getattr(document, "Name", None)
        with _registry_lock:
            if name:
                _session_ids.pop(name, None)
                _pending_saves.pop(name, None)
            if key and key in _registry:
                # Leave sidecar if path-keyed unclean; clean registry entry on close
                # without token is intentional for deleted docs — mark unlocked
                rec = _registry.pop(key, None)
                if rec and os.path.isabs(key) and key.lower().endswith(".fcstd"):
                    # Keep sidecar only if still held; release on delete of doc
                    _remove_sidecar(sidecar_path_for(key))
        _notify_gui()

    def _maybe_user_edit(self, document) -> None:
        if not is_enabled():
            return
        key = _doc_key_for_document(document)
        if not key:
            return
        if is_agent_mutating(key):
            return
        # Also check by doc_name keys that agent may have flagged
        name = getattr(document, "Name", None)
        if name and is_agent_mutating(name):
            return
        with _registry_lock:
            if key not in _registry:
                return
        mark_user_intervened(key)
        _notify_gui()


def register_observer() -> None:
    """Register DocumentLockObserver when enable_document_lock is true."""
    global _observer_registered
    if _observer_registered:
        return
    if not is_enabled():
        return
    try:
        import FreeCAD

        observer = DocumentLockObserver()
        FreeCAD.addDocumentObserver(observer)
        FreeCAD._mcp_document_lock_observer = observer
        _observer_registered = True
    except ImportError:
        pass


def register_lock_feature() -> None:
    """InitGui entry: observer + GUI indicator when enabled."""
    if not is_enabled():
        return
    register_observer()
    try:
        from lock_indicator import install_lock_indicator

        install_lock_indicator()
    except Exception as exc:
        try:
            import FreeCAD

            FreeCAD.Console.PrintWarning(f"[MCP] Lock indicator not installed: {exc}\n")
        except ImportError:
            pass
