from __future__ import annotations

# ruff: noqa: F403
from ._support import *

"""Authentication helpers for enforced dispatch."""

AUTHENTICATED_METHODS = frozenset(
    {
        "acquire_document_lock",
        "adopt_dirty_document",
        "update_document_lock",
        "heartbeat_document_lock",
        "lease_heartbeat_batch",
        "lease_reconcile",
        "release_document_lock",
        "save_document",
        "save_document_as",
        "finalize_document_edit",
        "get_request_status",
        "cancel_request",
        "shutdown_rpc_server",
        # Phase 16 actor-scoped GUI operations are read-only from the document
        # authority perspective, but must never accept a caller-supplied actor.
        "activate_document",
        "animate_placement",
        "capture_view_sequence",
        "capture_view_sequence_to_disk",
        "get_active_screenshot",
        "get_gui_state",
        "get_report_view",
        "get_selection",
        "open_document",
        "refresh_view",
        "reload_document",
        "repair_view_placements",
        "select_subshapes",
        "set_section_view",
        "set_tree_expanded",
    }
)


def is_read_only_execute(method, params):
    return (
        method == "execute_code"
        and len(params) > 1
        and isinstance(params[1], dict)
        and bool(params[1].get("read_only", False))
    )


def requires_authenticated_session(method, kind, VerbKind, read_only_execute):
    return (
        (kind == VerbKind.MUTATING and not read_only_execute)
        or method in AUTHENTICATED_METHODS
    ) and method not in {"handshake_v2", "invoke_v2"}


def elevate_rpc_session_identity_or_error(collaborators, identity_provider, identity=None):
    """Authenticate a transport session token into rpc_server request identity.

    Uses ``request_identity_provider`` (transport/GUI/invoke_v2 store), not
    ``document_lock`` request identity.  Idempotent when ``invoke_v2`` already
    elevated ``authenticated_session_id``.
    """
    if identity is None:
        identity = dict(identity_provider.get_request_identity())
    else:
        identity = dict(identity)
    if identity.get("authenticated_session_id"):
        return None
    if collaborators.session_manager is None:
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_REQUIRED",
            "error": "This operation requires authenticated RPC v2",
        }
    session_token = identity.get("rpc_session_token")
    runtime_id = identity.get("instance_id")
    if not session_token or not runtime_id:
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_REQUIRED",
            "error": (
                "This operation requires a handshake_v2 session and an "
                "immutable authenticated request envelope"
            ),
        }
    try:
        session = collaborators.session_manager.authenticate(
            session_token, mcp_runtime_id=runtime_id
        )
        identity["authenticated_session_id"] = session.session_id
        identity["mcp_process_started_at"] = session.mcp.process_started_at
        identity_provider.set_request_identity(**identity)
    except Exception as exc:
        error = collaborators.lease_protocol_public_error(
            exc, request_id=identity.get("request_id")
        )
        return {
            "success": False,
            "error_code": error["error"]["code"],
            "error": error["error"]["message"],
            "request_id": error.get("request_id"),
        }
    return None


def authenticate_session_or_error(collaborators, dl, identity):
    if collaborators.session_manager is None:
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_REQUIRED",
            "error": "This operation requires authenticated RPC v2",
        }
    session_token = identity.get("rpc_session_token")
    runtime_id = identity.get("instance_id")
    if not session_token or not runtime_id:
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_REQUIRED",
            "error": (
                "This operation requires a handshake_v2 session and an "
                "immutable authenticated request envelope"
            ),
        }
    try:
        session = collaborators.session_manager.authenticate(
            session_token, mcp_runtime_id=runtime_id
        )
        identity["authenticated_session_id"] = session.session_id
        identity["mcp_process_started_at"] = session.mcp.process_started_at
        dl.set_request_identity(**identity)
    except Exception as exc:
        error = collaborators.lease_protocol_public_error(
            exc, request_id=identity.get("request_id")
        )
        return {
            "success": False,
            "error_code": error["error"]["code"],
            "error": error["error"]["message"],
            "request_id": error.get("request_id"),
        }
    return None


def make_authorize_document(
    self, collaborators, method_spec, dl, resolve_doc_key, check_mutation_allowed
):
    def authorize_document(document_name):
        if collaborators.document_lease_service is not None:
            try:
                credential, document_identity = collaborators.credential_for_document(
                    document_name, dl.get_request_identity()
                )
                lease = collaborators.import_document_lease()
                allowed_states = {lease.LeaseState.LOCKED_IDLE}
                if method_spec.allowed_during_recovery:
                    allowed_states.add(lease.LeaseState.LOCKED_ERROR)
                record = collaborators.document_lease_service.authorize(
                    credential,
                    selector={
                        "document_session_uuid": document_identity.session_uuid,
                        "document_name": document_name,
                    },
                    allowed_states=allowed_states,
                )
                return {
                    "success": True,
                    "credential": credential,
                    "lease": record.to_public_dict(),
                }
            except Exception as exc:
                return collaborators.lease_service_error(
                    exc, request_id=dl.get_request_identity().get("request_id")
                )
        try:
            key = resolve_doc_key(doc_name=document_name)
        except Exception as exc:
            return {
                "success": False,
                "error_code": "document_not_locked",
                "error": f"Cannot resolve document {document_name!r}: {exc}",
            }
        return check_mutation_allowed(key)

    return authorize_document
