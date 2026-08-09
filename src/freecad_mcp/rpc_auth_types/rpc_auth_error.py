"""Compatibility alias for the canonical protocol error type."""

from __future__ import annotations

from .._shared.protocol.protocol_error import ProtocolError as RpcAuthError

__all__ = ["RpcAuthError"]
