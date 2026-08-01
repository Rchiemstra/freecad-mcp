"""Authenticated RPC v2 control-lane entrypoint."""

from __future__ import annotations

from ...lease_protocol import LeaseProtocolError


def _rpc_mod():
    from ... import rpc_server as rpc_mod

    return rpc_mod


def invoke_v2_control(self, payload):
    """Authenticated v2 entrypoint admitted only on the control lane."""
    method = payload.get("method") if isinstance(payload, dict) else None
    allowed = {
        "lease_heartbeat_batch",
        "lease_reconcile",
        "get_request_status",
        "cancel_request",
        "claim_acquisition_result",
        "acknowledge_acquisition_claim",
        "get_worker_status",
        "cancel_worker_job",
    }
    if method not in allowed:
        request_id = payload.get("request_id") if isinstance(payload, dict) else None
        return _rpc_mod().lease_protocol_public_error(
            LeaseProtocolError(
                "METHOD_NOT_CONTROL",
                "The requested method is not available on the control lane",
            ),
            request_id=request_id,
        )
    return self.invoke_v2(payload)
