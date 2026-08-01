from __future__ import annotations

import contextlib
import threading
from typing import Any

from .agent_mutation_ops import _agent_mutation_ctx, _mutation_state
from .module_aliases import install_module_aliases

_request_ctx = threading.local()

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
        with contextlib.suppress(AttributeError):
            delattr(_agent_mutation_ctx, "state")


def is_agent_mutating(doc_key: str, *, request_id: str | None = None) -> bool:
    """Return whether *doc_key* matches the current thread's valid context.

    Matching is deliberately exact.  Path aliases, document names, and the
    addon session UUID must be declared by the guarded request rather than
    inferred here.  Supplying ``request_id`` additionally requires an exact
    active-request match.

    On FreeCAD builds with DocumentMutationAuthority, RPC mutations also open an
    in-process core capability; this attribution marker remains the observer
    bridge so agent-scoped edits are not mistaken for user intervention.
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


install_module_aliases(__name__)
