from __future__ import annotations

# ruff: noqa: F403
from ._support import *
from .dispatch_core_enforcement_auth import (
    AUTHENTICATED_METHODS,
    auth_refusal_lane,
    elevate_rpc_session_identity_or_error,
    emit_auth_gate_refusal,
)

try:
    from automation_pause import admit_remote_write, finish_remote_write
except ImportError:  # pragma: no cover - package test layout
    from addon.FreeCADMCP.automation_pause import admit_remote_write, finish_remote_write

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

_PAUSE_GATED_LIFECYCLE_METHODS = frozenset(
    {"save_document", "save_document_as", "save_document_copy", "finalize_document_edit"}
)

# Pause admission needs only the read/write distinction.  Keep it local to the
# post-cutover dispatcher rather than reviving the retired document_lock
# classifier (which owned lease authority and unsafe-code policy).
_READ_ONLY_REMOTE_METHODS = frozenset(
    {
        "ping",
        "handshake_v2",
        "invoke_v2",
        "invoke_v2_control",
        "lease_heartbeat_batch",
        "lease_reconcile",
        "get_request_status",
        "cancel_request",
        "claim_acquisition_result",
        "acknowledge_acquisition_claim",
        "get_instance_info",
        "check_rpc_sync",
        "get_worker_status",
        "cancel_worker_job",
        "shutdown_rpc_server",
        "acquire_document_lock",
        "adopt_dirty_document",
        "get_document_lock",
        "list_document_locks",
        "heartbeat_document_lock",
        "update_document_lock",
        "release_document_lock",
        "force_release_stale_lock",
        "open_document",
        "list_documents",
        "activate_document",
        "snapshot",
        "inspect_references",
        "get_objects",
        "get_object",
        "get_parts_list",
        "get_active_screenshot",
        "capture_view_sequence",
        "capture_view_sequence_to_disk",
        "refresh_view",
        "get_selection",
        "get_gui_state",
        "get_report_view",
        "set_tree_expanded",
        "select_subshapes",
        "set_section_view",
        "get_recompute_log",
        "get_mutation_readiness",
        "spreadsheet_get_cells",
        "spreadsheet_list_aliases",
        "list_expressions",
        "diagnose_parametric",
        "get_sketch_diagnostics",
        "get_semantic_revisions",
    }
)


def _remote_write_method(method, params) -> bool:
    if method in _PAUSE_GATED_LIFECYCLE_METHODS:
        return True
    if method in _READ_ONLY_REMOTE_METHODS:
        return False
    return not (
        method == "execute_code"
        and len(params) > 1
        and isinstance(params[1], dict)
        and bool(params[1].get("read_only", False))
    )


def _pause_document_names(method, params) -> tuple[str, ...]:
    if not params:
        return ()
    if method == "execute_code" and len(params) > 1 and isinstance(params[1], dict):
        options = params[1]
        names = options.get("affected_documents")
        if isinstance(names, (list, tuple)):
            normalized = tuple(str(name) for name in names if name)
            if normalized:
                return normalized
        name = options.get("document")
        return (str(name),) if name else ()
    first = params[0]
    if isinstance(first, str) and first:
        return (first,)
    if isinstance(first, dict):
        name = first.get("document_name") or first.get("document")
        return (str(name),) if name else ()
    if len(params) > 1 and isinstance(params[1], dict):
        name = params[1].get("document")
        return (str(name),) if name else ()
    return ()


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
    admission = None
    if _remote_write_method(method, params):
        admission = admit_remote_write(method, _pause_document_names(method, params))
        if not admission.get("success"):
            return admission
    from ..cad_methods_ops.cad_mutation import cad_mutation_rpc_method

    try:
        with cad_mutation_rpc_method(method):
            return func(*params)
    finally:
        finish_remote_write(admission.get("token") if admission else None)
