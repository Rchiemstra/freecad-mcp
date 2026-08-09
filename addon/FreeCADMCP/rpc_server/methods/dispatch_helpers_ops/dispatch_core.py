from __future__ import annotations

# ruff: noqa: F403
from ._support import *
from .dispatch_core_enforcement_auth import (
    AUTHENTICATED_METHODS,
    auth_refusal_lane,
    elevate_rpc_session_identity_or_error,
    emit_auth_gate_refusal,
)

"""RPC dispatch chokepoint after native collaboration cutover."""

# Frozen Phase-18 lease stubs must reach their LEGACY_LEASE_AUTHORITY_REMOVED
# bodies. Session elevation applies only to live authenticated methods.
_LEGACY_LEASE_STUB_METHODS = frozenset(
    {
        "acquire_document_lock",
        "adopt_dirty_document",
        "update_document_lock",
        "heartbeat_document_lock",
        "lease_heartbeat_batch",
        "lease_reconcile",
        "release_document_lock",
    }
)


def dispatch(self, method, params):
    """Dispatch without creating a second document-authority layer.

    JSON-RPC v2 authenticates its immutable envelope in ``invoke_v2``.  CAD
    mutation methods enter FreeCAD's native compatibility-commit boundary at
    their operation adapters, so this transport layer only resolves and calls
    the public method.

    Plain RPC calls for actor-scoped GUI methods and other live authenticated
    verbs still need transport session elevation so ``request_identity_provider``
    exposes ``authenticated_session_id`` to ``request_actor``.  Legacy lease
    RPCs must reach their frozen deprecation stubs without that gate.
    """
    func = getattr(self, method, None)
    if func is None or method.startswith("_"):
        raise Exception(f'method "{method}" is not supported')
    if (
        method in AUTHENTICATED_METHODS
        and method not in _LEGACY_LEASE_STUB_METHODS
    ):
        collaborators = self._execution_collaborators
        identity_provider = collaborators.request_identity_provider()
        auth_error = elevate_rpc_session_identity_or_error(
            collaborators,
            identity_provider,
            identity_provider.get_request_identity(),
        )
        if auth_error is not None:
            emit_auth_gate_refusal(
                method=method,
                error_code=str(auth_error.get("error_code") or "AUTH_GATE_REFUSED"),
                lane=auth_refusal_lane(method),
                request_id=auth_error.get("request_id"),
            )
            return auth_error
    return func(*params)
