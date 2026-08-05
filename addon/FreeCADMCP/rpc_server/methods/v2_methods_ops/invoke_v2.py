"""Authenticated RPC v2 envelope dispatch entrypoint."""

from __future__ import annotations

from .invoke_v2_dispatch import (
    register_invoke_v2_inflight,
    run_invoke_v2_dispatch,
    set_invoke_v2_request_identity,
)
from .invoke_v2_replay import completed_replay_response, in_progress_replay_response

try:
    from ...._shared.protocol.protocol_error import ProtocolError as LeaseProtocolError
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.protocol_error import ProtocolError as LeaseProtocolError


def invoke_v2(self, payload):
    """Authenticate, de-duplicate, and dispatch one immutable RPC envelope."""
    collaborators = self._execution_collaborators
    request_id = payload.get("request_id") if isinstance(payload, dict) else None
    session_manager = collaborators.session_manager
    replay_cache = collaborators.request_replay_cache
    invocation_runtime_id = collaborators.runtime_id
    if session_manager is None or replay_cache is None:
        return collaborators.lease_protocol_public_error(
            LeaseProtocolError(
                "LEASE_PROTOCOL_UNAVAILABLE",
                "Authenticated RPC v2 is not configured for this profile",
            ),
            request_id=request_id,
        )
    identity_provider = collaborators.request_identity_provider()
    transport_identity = identity_provider.get_request_identity()
    try:
        session, envelope = session_manager.authenticate_envelope(
            payload,
            transport_mcp_runtime_id=transport_identity.get("instance_id"),
        )
        if envelope.lease_credentials:
            raise LeaseProtocolError(
                "LEGACY_LEASE_AUTHORITY_REMOVED",
                "Document lease credentials are no longer accepted",
            )
        forbidden = {
            "handshake_v2",
            "invoke_v2",
            "invoke_v2_control",
            "shutdown_rpc_server",
            "force_release_stale_lock",
        }
        if envelope.method in forbidden or envelope.method.startswith("_"):
            raise LeaseProtocolError(
                "METHOD_NOT_ALLOWED",
                "The requested method is not available through invoke_v2",
            )
        target = getattr(self, envelope.method, None)
        if target is None or not callable(target):
            raise LeaseProtocolError(
                "UNKNOWN_METHOD", "The requested RPC method is not registered"
            )
        collaborators.validate_generated_operation_envelope(envelope)
        replay = replay_cache.claim(
            session.mcp.runtime_id,
            envelope,
        )
        if replay.status == "completed":
            return completed_replay_response(
                replay=replay,
                envelope=envelope,
                session=session,
                invocation_runtime_id=invocation_runtime_id,
                claim_store=None,
            )
        if replay.status == "in_progress":
            return in_progress_replay_response(
                envelope=envelope,
                invocation_runtime_id=invocation_runtime_id,
            )

        params, inflight = register_invoke_v2_inflight(
            collaborators=collaborators,
            self=self,
            session=session,
            envelope=envelope,
            target=target,
            replay_cache=replay_cache,
        )
        previous_identity = identity_provider.get_request_identity()
        set_invoke_v2_request_identity(
            identity_provider=identity_provider,
            session=session,
            envelope=envelope,
            transport_identity=transport_identity,
        )
        self._inflight_context.value = inflight
        handler_state = {"status": "failed", "finalized": False}
        try:
            return run_invoke_v2_dispatch(
                collaborators=collaborators,
                self=self,
                session=session,
                envelope=envelope,
                params=params,
                inflight=inflight,
                invocation_runtime_id=invocation_runtime_id,
                replay_cache=replay_cache,
                handler_state=handler_state,
            )
        finally:
            if hasattr(self._inflight_context, "value"):
                del self._inflight_context.value
            identity_provider.set_request_identity(**previous_identity)
    except Exception as exc:
        return collaborators.lease_protocol_public_error(
            exc, request_id=request_id
        )
