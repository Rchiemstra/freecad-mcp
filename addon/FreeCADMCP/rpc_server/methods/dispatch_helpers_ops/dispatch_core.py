from __future__ import annotations

# ruff: noqa: F403
from ._support import *
from .dispatch_core_enforcement_auth import (
    AUTHENTICATED_METHODS,
    elevate_rpc_session_identity_or_error,
)

"""RPC dispatch chokepoint after native collaboration cutover."""


def dispatch(self, method, params):
    """Dispatch without creating a second document-authority layer.

    JSON-RPC v2 authenticates its immutable envelope in ``invoke_v2``.  CAD
    mutation methods enter FreeCAD's native compatibility-commit boundary at
    their operation adapters, so this transport layer only resolves and calls
    the public method.

    Plain RPC calls for actor-scoped GUI methods still need transport session
    elevation so ``request_identity_provider`` exposes
    ``authenticated_session_id`` to ``request_actor``.
    """
    func = getattr(self, method, None)
    if func is None or method.startswith("_"):
        raise Exception(f'method "{method}" is not supported')
    if method in AUTHENTICATED_METHODS:
        collaborators = self._execution_collaborators
        identity_provider = collaborators.request_identity_provider()
        auth_error = elevate_rpc_session_identity_or_error(
            collaborators,
            identity_provider,
            identity_provider.get_request_identity(),
        )
        if auth_error is not None:
            return auth_error
    return func(*params)
