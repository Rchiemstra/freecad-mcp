"""Extracted ``_SessionRecord`` for ARCH002 (workstream 1G)."""

from __future__ import annotations

from dataclasses import dataclass

from .session_context import SessionContext


@dataclass
class _SessionRecord:
    context: SessionContext
    token_digest: str
    expires_monotonic: float
    revoked: bool = False
    revocation_reason: str | None = None


_SessionRecord.__module__ = "rpc_server.lease_protocol"
