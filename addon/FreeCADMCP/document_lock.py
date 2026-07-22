"""Per-document renewable write lease for MCP agents.

Pure/unit-testable core: lease registry, atomic sidecar lock files, staleness
checks, and Save As / first-save key migration. FreeCAD and Qt are imported
lazily so the module loads under the stubbed unit harness.

When ``enable_document_lock`` is false (default), nothing is registered, no
sidecars are written, and callers should treat this module as inert.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import threading
import time
import uuid
import secrets
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


# FreeCAD adds this addon directory directly to ``sys.path`` and imports this
# file as ``document_lock``.  Package-aware callers (including the test suite)
# import the same file as ``addon.FreeCADMCP.document_lock``.  Without an early
# alias Python executes the file twice, producing two lease registries, two
# settings functions, and two request-identity thread locals.  Whichever name
# loads first owns the single module object; publishing both names here makes
# every later import resolve to that same object in either environment.
_CANONICAL_MODULE_NAME = "addon.FreeCADMCP.document_lock"
_FREECAD_MODULE_NAME = "document_lock"
_MODULE_ALIASES = (_CANONICAL_MODULE_NAME, _FREECAD_MODULE_NAME)


def _install_module_aliases() -> None:
    current = sys.modules.get(__name__)
    if current is None:  # pragma: no cover - import machinery always sets it
        return

    # The normal path has no existing peer.  The existing-module branch makes
    # reloads and unusual concurrent embedding setups converge conservatively
    # on the module object that was published first.
    owner = next(
        (
            module
            for alias in _MODULE_ALIASES
            if (module := sys.modules.get(alias)) is not None
            and module is not current
        ),
        current,
    )
    for alias in _MODULE_ALIASES:
        sys.modules[alias] = owner


_install_module_aliases()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

_runtime_lease_mode: str | None = None

def _settings_path() -> Path:
    try:
        import FreeCAD

        return Path(FreeCAD.getUserAppDataDir()) / "freecad_mcp_settings.json"
    except ImportError:
        return Path.home() / "freecad_mcp_settings.json"


def _read_settings() -> dict[str, Any]:
    path = _settings_path()
    if not path.is_file():
        # A genuinely new ordinary profile follows the central settings
        # default and starts in observe mode.  An existing empty JSON object
        # remains the legacy explicit-off policy during migration.
        return {
            "document_lease_mode": "observe",
            "enable_document_lock": True,
            "document_lock_enforcement": False,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    # Missing/corrupt policy must never turn a previously protected runtime
    # into a direct-call listener.  The central settings reader uses the same
    # fail-closed mode and prevents server startup until the file is repaired.
    return {
        "document_lease_mode": "enforce",
        "enable_document_lock": True,
        "document_lock_enforcement": True,
        "_configuration_error": "invalid document lease settings",
    }


def configure_runtime_lease_mode(mode: str) -> None:
    """Latch one validated mode for the lifetime of the lease runtime.

    Settings are intentionally not a per-request authorization input.  A mode
    change is admitted only by ``initialize_document_lease_runtime``, which
    first proves that no active/recovery records would be weakened.
    """

    normalized = str(mode or "")
    if normalized not in {"off", "observe", "enforce"}:
        raise ValueError("document lease mode must be off, observe, or enforce")
    global _runtime_lease_mode
    _runtime_lease_mode = normalized


def get_runtime_lease_mode() -> str | None:
    return _runtime_lease_mode


def is_enabled() -> bool:
    """True when document lock infrastructure (observer/GUI/sidecars) is on."""
    if _runtime_lease_mode is not None:
        return _runtime_lease_mode != "off"
    data = _read_settings()
    mode = data.get("document_lease_mode")
    if mode in {"off", "observe", "enforce"}:
        return mode != "off"
    return bool(data.get("enable_document_lock", False))


def is_enforcement_enabled() -> bool:
    """True when mutating RPC verbs must present a valid owned lease."""
    if _runtime_lease_mode is not None:
        return _runtime_lease_mode == "enforce"
    data = _read_settings()
    mode = data.get("document_lease_mode")
    if mode in {"off", "observe", "enforce"}:
        return mode == "enforce"
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
    ACQUIRING = "ACQUIRING"
    LOCKED_IDLE = "LOCKED_IDLE"
    LOCKED_EDITING = "LOCKED_EDITING"
    LOCKED_RECOMPUTING = "LOCKED_RECOMPUTING"
    LOCKED_SAVING = "LOCKED_SAVING"
    LOCKED_ERROR = "LOCKED_ERROR"
    USER_INTERVENED = "USER_INTERVENED"
    CANCELLING = "CANCELLING"
    RELEASING = "RELEASING"
    UNLOCKED_SAVED = "UNLOCKED_SAVED"
    UNLOCKED_DIRTY = "UNLOCKED_DIRTY"
    STALE = "STALE"


@dataclass
class LeaseRecord:
    doc_key: str
    doc_name: str
    token: str = field(repr=False)
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
    state: str = LeaseState.LOCKED_IDLE.value
    rpc_port: int | None = None
    lease_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    generation: int = 1
    state_revision: int = 1
    record_revision: int = 1
    heartbeat_sequence: int = 0
    last_mutation_revision: int = 0
    last_verified_save_revision: int = 0
    user_intervened: bool = False
    request_id: str | None = None
    error_info: dict[str, Any] | None = None
    document_session_uuid: str = ""
    token_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("token", None)
        payload.pop("token_fingerprint", None)
        return payload

    def to_sidecar_dict(self) -> dict[str, Any]:
        payload = self.to_dict()
        digest = self.token_fingerprint or hashlib.sha256(
            self.token.encode("utf-8")
        ).hexdigest()
        payload["token_fingerprint"] = f"sha256:{digest.removeprefix('sha256:')}"
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LeaseRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        values = {k: v for k, v in data.items() if k in known}
        raw_token = str(values.get("token") or "")
        fingerprint = str(values.get("token_fingerprint") or "")
        if raw_token and not fingerprint:
            fingerprint = "sha256:" + hashlib.sha256(
                raw_token.encode("utf-8")
            ).hexdigest()
        # A sidecar is public coordination metadata, never credential custody.
        values["token"] = ""
        values["token_fingerprint"] = fingerprint
        return cls(**values)


# ---------------------------------------------------------------------------
# Thread-local request identity + GUI request mutation attribution
# ---------------------------------------------------------------------------

_request_ctx = threading.local()


@dataclass
class _AgentMutationState:
    """Attribution owned by exactly one executing thread.

    FreeCAD document observers are called synchronously on the thread that is
    changing the live document.  Keeping this state thread-local therefore
    prevents an XML-RPC worker (or another GUI callback) from making unrelated
    changes look agent-authored.  Version-2 callers use one exact document-key
    set for the whole request.  The per-key counters exist solely for the
    compatibility facade used by version-1 integrations.
    """

    request_id: str = ""
    document_keys: frozenset[str] = frozenset()
    depth: int = 0
    violation: str = ""
    legacy_counts: dict[str, int] = field(default_factory=dict)


_agent_mutation_ctx = threading.local()


def _mutation_state(*, create: bool = False) -> _AgentMutationState | None:
    state = getattr(_agent_mutation_ctx, "state", None)
    if state is None and create:
        state = _AgentMutationState()
        _agent_mutation_ctx.state = state
    return state


def _normalized_mutation_keys(document_keys) -> frozenset[str]:
    if isinstance(document_keys, str):
        document_keys = (document_keys,)
    try:
        normalized_values = set()
        for value in document_keys:
            if value is None:
                continue
            normalized = str(value).strip()
            if normalized:
                normalized_values.add(normalized)
        normalized = frozenset(normalized_values)
    except TypeError as exc:
        raise ValueError("document mutation scope must be iterable") from exc
    if not normalized:
        raise ValueError("document mutation scope must not be empty")
    return normalized


def begin_agent_mutation_scope(request_id: str, document_keys) -> bool:
    """Begin an exact, request-scoped GUI mutation attribution context.

    Safe nesting is allowed only for the same non-empty request ID and the
    same exact set of declared document keys.  A different request, a changed
    scope, or mixing this API with the legacy marker poisons attribution until
    the outermost scope exits, so observers fail closed instead of accepting a
    re-entrant or undeclared mutation.
    """

    normalized_request_id = str(request_id or "").strip()
    if not normalized_request_id:
        raise ValueError("agent mutation request_id must not be empty")
    normalized_keys = _normalized_mutation_keys(document_keys)
    state = _mutation_state(create=True)
    assert state is not None
    if state.legacy_counts:
        state.violation = "request-scoped mutation nested inside legacy attribution"
    if state.depth == 0:
        state.request_id = normalized_request_id
        state.document_keys = normalized_keys
        state.violation = state.violation or ""
    elif (
        state.request_id != normalized_request_id
        or state.document_keys != normalized_keys
    ):
        state.violation = "nested mutation request or document scope mismatch"
    state.depth += 1
    return not state.violation


def end_agent_mutation_scope(request_id: str, document_keys) -> bool:
    """End one reference to an exact GUI mutation scope.

    Mismatched teardown is itself fail-closed.  It does not expose a still
    active outer request as valid attribution, but the state is cleared when
    the outermost reference has unwound so a bad request cannot poison later
    independent GUI work.
    """

    normalized_request_id = str(request_id or "").strip()
    normalized_keys = _normalized_mutation_keys(document_keys)
    state = _mutation_state()
    if state is None or state.depth <= 0:
        return False
    if (
        state.request_id != normalized_request_id
        or state.document_keys != normalized_keys
    ):
        state.violation = "mutation scope teardown mismatch"
    state.depth -= 1
    valid = not state.violation
    if state.depth == 0:
        state.request_id = ""
        state.document_keys = frozenset()
        state.violation = ""
        if not state.legacy_counts:
            try:
                delattr(_agent_mutation_ctx, "state")
            except AttributeError:
                pass
    return valid


def get_agent_mutation_context() -> dict[str, Any]:
    """Return a token-free snapshot of the current thread's attribution."""

    state = _mutation_state()
    if state is None:
        return {
            "active": False,
            "request_id": None,
            "document_keys": (),
            "depth": 0,
            "valid": False,
            "violation": None,
            "thread_id": threading.get_ident(),
            "legacy": False,
        }
    strict_active = state.depth > 0
    legacy_active = bool(state.legacy_counts)
    return {
        "active": strict_active or legacy_active,
        "request_id": state.request_id if strict_active else None,
        "document_keys": tuple(
            sorted(
                state.document_keys
                if strict_active
                else state.legacy_counts.keys()
            )
        ),
        "depth": state.depth if strict_active else sum(state.legacy_counts.values()),
        "valid": bool(
            (strict_active and not state.violation and not legacy_active)
            or (legacy_active and not strict_active)
        ),
        "violation": state.violation or None,
        "thread_id": threading.get_ident(),
        "legacy": legacy_active and not strict_active,
    }


def set_request_identity(
    *,
    instance_id: str | None = None,
    client: str | None = None,
    pid: int | None = None,
    host: str | None = None,
    lease_token: str | None = None,
    rpc_port: int | None = None,
    request_id: str | None = None,
    rpc_session_token: str | None = None,
    lease_id: str | None = None,
    lease_generation: int | None = None,
    document_session_uuid: str | None = None,
    lease_credentials: list[dict[str, Any]] | None = None,
    mcp_process_started_at: str | None = None,
    agent_id: str | None = None,
    authenticated_session_id: str | None = None,
) -> None:
    _request_ctx.instance_id = instance_id
    _request_ctx.client = client
    _request_ctx.pid = pid
    _request_ctx.host = host
    _request_ctx.lease_token = lease_token
    _request_ctx.rpc_port = rpc_port
    _request_ctx.request_id = request_id
    _request_ctx.rpc_session_token = rpc_session_token
    _request_ctx.lease_id = lease_id
    _request_ctx.lease_generation = lease_generation
    _request_ctx.document_session_uuid = document_session_uuid
    _request_ctx.lease_credentials = list(lease_credentials or [])
    _request_ctx.mcp_process_started_at = mcp_process_started_at
    _request_ctx.agent_id = agent_id
    _request_ctx.authenticated_session_id = authenticated_session_id


def clear_request_identity() -> None:
    for attr in (
        "instance_id",
        "client",
        "pid",
        "host",
        "lease_token",
        "rpc_port",
        "request_id",
        "rpc_session_token",
        "lease_id",
        "lease_generation",
        "document_session_uuid",
        "lease_credentials",
        "mcp_process_started_at",
        "agent_id",
        "authenticated_session_id",
    ):
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
        "request_id": getattr(_request_ctx, "request_id", None),
        "rpc_session_token": getattr(_request_ctx, "rpc_session_token", None),
        "lease_id": getattr(_request_ctx, "lease_id", None),
        "lease_generation": getattr(_request_ctx, "lease_generation", None),
        "document_session_uuid": getattr(
            _request_ctx, "document_session_uuid", None
        ),
        "lease_credentials": list(
            getattr(_request_ctx, "lease_credentials", []) or []
        ),
        "mcp_process_started_at": getattr(
            _request_ctx, "mcp_process_started_at", None
        ),
        "agent_id": getattr(_request_ctx, "agent_id", None),
        "authenticated_session_id": getattr(
            _request_ctx, "authenticated_session_id", None
        ),
    }


def begin_agent_mutation(doc_key: str) -> None:
    """Compatibility facade for legacy per-key mutation markers.

    Version-2 GUI mutation paths must use :func:`begin_agent_mutation_scope`
    so a real request ID and its complete declared scope are inseparable.
    """

    key = str(doc_key or "").strip()
    if not key:
        return
    state = _mutation_state(create=True)
    assert state is not None
    if state.depth:
        state.violation = "legacy attribution nested inside request-scoped mutation"
    state.legacy_counts[key] = state.legacy_counts.get(key, 0) + 1


def end_agent_mutation(doc_key: str) -> None:
    key = str(doc_key or "").strip()
    state = _mutation_state()
    if state is None or not key:
        return
    count = state.legacy_counts.get(key, 0)
    if count <= 1:
        state.legacy_counts.pop(key, None)
    else:
        state.legacy_counts[key] = count - 1
    if not state.legacy_counts and state.depth == 0:
        try:
            delattr(_agent_mutation_ctx, "state")
        except AttributeError:
            pass


def is_agent_mutating(doc_key: str, *, request_id: str | None = None) -> bool:
    """Return whether *doc_key* matches the current thread's valid context.

    Matching is deliberately exact.  Path aliases, document names, and the
    addon session UUID must be declared by the guarded request rather than
    inferred here.  Supplying ``request_id`` additionally requires an exact
    active-request match.
    """

    key = str(doc_key or "").strip()
    if not key:
        return False
    state = _mutation_state()
    if state is None:
        return False
    if state.depth:
        if state.violation or state.legacy_counts:
            return False
        if request_id is not None and state.request_id != str(request_id).strip():
            return False
        return key in state.document_keys
    if request_id is not None:
        # Legacy markers have no authenticated request identity.
        return False
    return state.legacy_counts.get(key, 0) > 0


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


_SENSITIVE_SIDECAR_FIELDS = frozenset(
    {
        "auth_secret",
        "auth_token",
        "bearer_token",
        "client_proof",
        "hmac",
        "lease_token",
        "password",
        "private_key",
        "profile_secret",
        "proof",
        "rpc_session_token",
        "secret",
        "secret_fingerprint",
        "server_proof",
        "session_token",
        "signature",
        "token",
        "token_digest",
        "token_fingerprint",
    }
)


def _is_sensitive_sidecar_field(key: Any) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_SIDECAR_FIELDS or normalized.endswith(
        ("_password", "_proof", "_secret", "_signature", "_token")
    )


def _collect_sidecar_secrets(value: Any, secrets_out: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _is_sensitive_sidecar_field(key):
                _collect_secret_strings(child, secrets_out)
                continue
            _collect_sidecar_secrets(child, secrets_out)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_sidecar_secrets(child, secrets_out)


def _collect_secret_strings(value: Any, secrets_out: set[str]) -> None:
    if isinstance(value, str):
        if value:
            secrets_out.add(value)
        return
    if isinstance(value, dict):
        for child in value.values():
            _collect_secret_strings(child, secrets_out)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_secret_strings(child, secrets_out)


def _redact_sidecar_diagnostic(value: Any, secrets: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "<redacted>"
                if _is_sensitive_sidecar_field(key)
                else _redact_sidecar_diagnostic(child, secrets)
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_sidecar_diagnostic(child, secrets) for child in value]
    if isinstance(value, tuple):
        return [_redact_sidecar_diagnostic(child, secrets) for child in value]
    if isinstance(value, str):
        safe = value
        for secret in secrets:
            safe = safe.replace(secret, "[REDACTED]")
        return safe
    return value


def _public_sidecar_payload(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    try:
        return LeaseRecord.from_dict(data).to_dict()
    except Exception:
        secrets_found: set[str] = set()
        _collect_sidecar_secrets(data, secrets_found)
        return _redact_sidecar_diagnostic(data, secrets_found)


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
    global _runtime_lease_mode
    with _registry_lock:
        _registry.clear()
        _session_ids.clear()
        _pending_saves.clear()
    _runtime_lease_mode = None
    if hasattr(_agent_mutation_ctx, "state"):
        delattr(_agent_mutation_ctx, "state")
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

    token = secrets.token_urlsafe(32)
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
        state=LeaseState.LOCKED_IDLE.value,
        rpc_port=rpc_port,
        document_session_uuid=(ensure_session_id(doc_name) if doc_name else str(uuid.uuid4())),
    )

    with _registry_lock:
        existing = _registry.get(doc_key)
        if existing and not _is_stale(existing, now=now):
            if existing.instance_id == instance_id:
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
                # Same instance re-acquires: refresh token + heartbeat in place
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
                # Staleness is never permission to delete or overwrite.
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

            if not _create_sidecar_exclusive(side, record.to_sidecar_dict()):
                # Race: another process created it first
                raced = _read_sidecar(side)
                return {
                    "success": False,
                    "error_code": "document_locked_by_other",
                    "error": "Failed to create exclusive sidecar (lost race)",
                    "lease": _public_sidecar_payload(raced),
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
        if not token or not hmac.compare_digest(str(record.token), str(token)):
            return {
                "success": False,
                "error_code": "invalid_lease_token",
                "error": "Lease token does not match",
                "lease": record.to_dict(),
            }
        record.last_heartbeat = time.time()
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
        previous = record.state
        record.state = new_state
        record.state_revision += 1
        record.record_revision += 1
        record.last_heartbeat = time.time()
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
                **asdict(record),
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
        # ``migrate_lease_key`` is invoked only after the save observer has
        # verified the destination.  Publish that completed save as idle and
        # clean so the compatibility lifecycle can finalize normally.
        migrated.state = LeaseState.LOCKED_IDLE.value
        migrated.document_dirty = False
        migrated.last_verified_save_revision = migrated.last_mutation_revision

        side_new = sidecar_path_for(new_key)
        expected_fingerprint = record.to_sidecar_dict()["token_fingerprint"]
        if side_new.is_file():
            existing = _read_sidecar(side_new)
            if existing and not hmac.compare_digest(
                str(existing.get("token_fingerprint") or ""),
                expected_fingerprint,
            ):
                other = LeaseRecord.from_dict(existing) if existing else None
                if other and not _is_stale(other) and pid_alive(other.pid):
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

        if not _create_sidecar_exclusive(side_new, migrated.to_sidecar_dict()):
            # If we own a pre-created destination (Save As held it), overwrite
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
        record.generation += 1
        # Rotate to an unreturned value.  The old agent can neither mutate nor
        # heartbeat this generation and must not automatically reacquire.
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


def check_mutation_allowed(
    doc_key: str,
    *,
    identity: dict[str, Any] | None = None,
    allowed_states: set[str] | None = None,
) -> dict[str, Any]:
    """Enforce exact owner, document, generation, and token authorization."""
    identity = dict(identity or get_request_identity())
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
                "The revoked agent may not automatically reacquire it."
            ),
            "lease": record.to_dict(),
        }

    permitted = allowed_states or {LeaseState.LOCKED_IDLE.value}
    if record.state not in permitted:
        return {
            "success": False,
            "error_code": "lease_state_blocks_mutation",
            "error": f"Lease state {record.state} does not permit this mutation",
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

    credentials = identity.get("lease_credentials") or []
    if credentials:
        matched = next(
            (
                item
                for item in credentials
                if isinstance(item, dict)
                and (
                    item.get("lease_id") == record.lease_id
                    or (
                        record.document_session_uuid
                        and item.get("document_session_uuid")
                        == record.document_session_uuid
                    )
                )
            ),
            None,
        )
        if matched is None:
            return {
                "success": False,
                "error_code": "lease_credential_missing",
                "error": "Request has no credential for this document",
                "lease": record.to_dict(),
            }
        if matched.get("lease_id") != record.lease_id:
            return {
                "success": False,
                "error_code": "lease_id_mismatch",
                "error": "Lease identifier does not match the active lease",
                "lease": record.to_dict(),
            }
        if int(matched.get("generation", 0)) != record.generation:
            return {
                "success": False,
                "error_code": "lease_generation_mismatch",
                "error": "Lease generation has been fenced",
                "lease": record.to_dict(),
            }
        token = matched.get("token")
    else:
        if identity.get("lease_id") and identity.get("lease_id") != record.lease_id:
            return {
                "success": False,
                "error_code": "lease_id_mismatch",
                "error": "Lease identifier does not match the active lease",
                "lease": record.to_dict(),
            }
        generation = identity.get("lease_generation")
        if generation is not None and int(generation) != record.generation:
            return {
                "success": False,
                "error_code": "lease_generation_mismatch",
                "error": "Lease generation has been fenced",
                "lease": record.to_dict(),
            }
        session_uuid = identity.get("document_session_uuid")
        if (
            session_uuid
            and record.document_session_uuid
            and session_uuid != record.document_session_uuid
        ):
            return {
                "success": False,
                "error_code": "document_session_mismatch",
                "error": "Document session identity does not match",
                "lease": record.to_dict(),
            }

    if not token:
        return {
            "success": False,
            "error_code": "missing_lease_token",
            "error": "Every mutation must present the active lease token",
            "lease": record.to_dict(),
        }
    if not hmac.compare_digest(str(token), str(record.token)):
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
    "handshake_v2": (VerbKind.LIFECYCLE, _none_doc),
    "invoke_v2": (VerbKind.LIFECYCLE, _none_doc),
    "invoke_v2_control": (VerbKind.LIFECYCLE, _none_doc),
    "lease_heartbeat_batch": (VerbKind.LIFECYCLE, _none_doc),
    "lease_reconcile": (VerbKind.LIFECYCLE, _none_doc),
    "get_request_status": (VerbKind.LIFECYCLE, _none_doc),
    "cancel_request": (VerbKind.LIFECYCLE, _none_doc),
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
    "update_document_lock": (VerbKind.LIFECYCLE, _none_doc),
    "release_document_lock": (VerbKind.LIFECYCLE, _none_doc),
    "save_document": (VerbKind.LIFECYCLE, _none_doc),
    "save_document_as": (VerbKind.LIFECYCLE, _none_doc),
    "finalize_document_edit": (VerbKind.LIFECYCLE, _none_doc),
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
    "insert_part_from_library": (VerbKind.MUTATING, _params0_doc),
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
    "repair_view_placements": (VerbKind.MUTATING, _params0_doc),
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


def validate_unsafe_execute_scope(
    code: str, declared_documents: set[str]
) -> dict[str, Any]:
    """Conservatively validate explicitly enabled public live Python.

    This is scope validation, not a Python sandbox.  Code that can obscure
    document discovery is rejected because the GUI guard cannot prove that its
    declared credential set is complete.  Repository-generated operations are
    separately audited and do not use this public unsafe path.
    """
    import ast

    violations: list[str] = []
    referenced: set[str] = set()
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return {
            "ok": False,
            "referenced_documents": [],
            "violations": [f"syntax_error:{exc.lineno or 0}"],
        }

    obscuring_calls = {
        "__import__",
        "compile",
        "delattr",
        "eval",
        "exec",
        "getattr",
        "globals",
        "locals",
        "setattr",
        "vars",
    }
    document_lifecycle_calls = {
        "closeDocument",
        "newDocument",
        "open",
        "openDocument",
    }
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            violations.append(f"imports_not_allowed:{getattr(node, 'lineno', 0)}")
            continue
        if isinstance(node, ast.Attribute) and node.attr == "ActiveDocument":
            violations.append(
                f"active_document_not_allowed:{getattr(node, 'lineno', 0)}"
            )
            continue
        if isinstance(node, ast.Name) and node.id == "ActiveDocument":
            violations.append(
                f"active_document_not_allowed:{getattr(node, 'lineno', 0)}"
            )
            continue
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        call_name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else ""
        )
        if call_name in obscuring_calls:
            violations.append(
                f"dynamic_code_or_lookup_not_allowed:{call_name}:"
                f"{getattr(node, 'lineno', 0)}"
            )
        if call_name in document_lifecycle_calls:
            violations.append(
                f"document_lifecycle_not_allowed:{call_name}:"
                f"{getattr(node, 'lineno', 0)}"
            )
        if call_name != "getDocument":
            continue
        if (
            not node.args
            or not isinstance(node.args[0], ast.Constant)
            or not isinstance(node.args[0].value, str)
        ):
            violations.append(
                f"dynamic_document_lookup_not_allowed:{getattr(node, 'lineno', 0)}"
            )
            continue
        referenced.add(node.args[0].value)

    undeclared = sorted(referenced - set(declared_documents))
    if undeclared:
        violations.append("undeclared_documents:" + ",".join(undeclared))
    return {
        "ok": not violations,
        "referenced_documents": sorted(referenced),
        "violations": sorted(set(violations)),
    }


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
            pre = dict(record.to_sidecar_dict())
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
                transition_lease(
                    dest,
                    token,
                    LeaseState.LOCKED_IDLE.value,
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
