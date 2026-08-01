"""Authenticated RPC v2 handshake entrypoint."""

from __future__ import annotations


def _rpc_mod():
    from ... import rpc_server as rpc_mod

    return rpc_mod


def handshake_v2(self, payload):
    """Authenticate one exact MCP runtime before any lease operation."""
    rpc_mod = _rpc_mod()
    if rpc_mod.rpc_session_manager is None:
        return {
            "ok": False,
            "error": {
                "code": "LEASE_PROTOCOL_UNAVAILABLE",
                "message": "Authenticated RPC v2 is not configured for this profile",
            },
        }
    try:
        return rpc_mod.rpc_session_manager.perform_handshake(payload)
    except Exception as exc:
        return rpc_mod.lease_protocol_public_error(exc)
