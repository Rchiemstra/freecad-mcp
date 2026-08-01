"""Extracted ``VerifiedHandshakeResponse`` for ARCH002 (workstream 1G)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .runtime_manifest import RuntimeManifest


@dataclass(frozen=True)
class VerifiedHandshakeResponse:
    client_nonce: str
    server_nonce: str
    session_id: str
    session_token: str = field(repr=False)
    session_expires_at: str
    manifest: RuntimeManifest
    negotiated_features: tuple[str, ...]


VerifiedHandshakeResponse.__module__ = "rpc_server.lease_protocol"
