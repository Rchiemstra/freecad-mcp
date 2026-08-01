"""Authenticated RPC v2 envelope dispatch entrypoint."""

from __future__ import annotations

from ...lease_protocol import LeaseProtocolError
from ...mutation_guard import make_method_spec
from .invoke_v2_dispatch import (
    register_invoke_v2_inflight,
    run_invoke_v2_dispatch,
    set_invoke_v2_request_identity,
)
from .invoke_v2_replay import completed_replay_response, in_progress_replay_response


def _rpc_mod():
    from ... import rpc_server as rpc_mod

    return rpc_mod


def invoke_v2(self, payload):
    """Authenticate, de-duplicate, and dispatch one immutable RPC envelope."""
    rpc_mod = _rpc_mod()
    request_id = payload.get("request_id") if isinstance(payload, dict) else None
    session_manager = rpc_mod.rpc_session_manager
    replay_cache = rpc_mod.rpc_request_replay_cache
    invocation_runtime_id = rpc_mod.rpc_server_runtime_id
    lease_service = rpc_mod.document_lease_service
    if session_manager is None or replay_cache is None:
        return rpc_mod.lease_protocol_public_error(
            LeaseProtocolError(
                "LEASE_PROTOCOL_UNAVAILABLE",
                "Authenticated RPC v2 is not configured for this profile",
            ),
            request_id=request_id,
        )
    dl = rpc_mod._import_document_lock()
    transport_identity = dl.get_request_identity()
    try:
        session, envelope = session_manager.authenticate_envelope(
            payload,
            transport_mcp_runtime_id=transport_identity.get("instance_id"),
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
        rpc_mod._validate_generated_operation_envelope(envelope)
        request_kind, _request_extractor = dl.classify_verb(envelope.method)
        method_spec = make_method_spec(envelope.method, request_kind.value)
        lease_affecting = method_spec.pin_replay_for_lease_lifetime
        if envelope.method == "execute_code":
            options = envelope.params.get("options")
            if isinstance(options, dict) and options.get("read_only") is True:
                lease_affecting = False
        replay = replay_cache.claim(
            session.mcp.runtime_id,
            envelope,
            pin_to_owner_leases=lease_affecting,
        )
        if replay.status == "completed":
            return completed_replay_response(
                replay=replay,
                envelope=envelope,
                session=session,
                invocation_runtime_id=invocation_runtime_id,
                claim_store=rpc_mod.rpc_acquisition_claim_store,
            )
        if replay.status == "in_progress":
            return in_progress_replay_response(
                envelope=envelope,
                invocation_runtime_id=invocation_runtime_id,
            )

        params, inflight = register_invoke_v2_inflight(
            rpc_mod=rpc_mod,
            self=self,
            session=session,
            envelope=envelope,
            target=target,
            lease_affecting=lease_affecting,
            replay_cache=replay_cache,
        )
        previous_identity = dl.get_request_identity()
        set_invoke_v2_request_identity(
            dl=dl,
            session=session,
            envelope=envelope,
            transport_identity=transport_identity,
        )
        self._inflight_context.value = inflight
        handler_state = {"status": "failed", "finalized": False}
        try:
            return run_invoke_v2_dispatch(
                rpc_mod=rpc_mod,
                self=self,
                session=session,
                envelope=envelope,
                params=params,
                inflight=inflight,
                lease_service=lease_service,
                lease_affecting=lease_affecting,
                invocation_runtime_id=invocation_runtime_id,
                replay_cache=replay_cache,
                handler_state=handler_state,
            )
        finally:
            if hasattr(self._inflight_context, "value"):
                del self._inflight_context.value
            dl.set_request_identity(**previous_identity)
    except Exception as exc:
        return rpc_mod.lease_protocol_public_error(exc, request_id=request_id)
