"""Authenticated RPC v2 handshake entrypoint."""

from __future__ import annotations


def handshake_v2(self, payload):
    """Authenticate one exact MCP runtime before any lease operation."""
    collaborators = self._execution_collaborators
    if collaborators.session_manager is None:
        return {
            "ok": False,
            "error": {
                "code": "LEASE_PROTOCOL_UNAVAILABLE",
                "message": "Authenticated RPC v2 is not configured for this profile",
            },
        }
    try:
        return collaborators.session_manager.perform_handshake(payload)
    except Exception as exc:
        return collaborators.lease_protocol_public_error(exc)
