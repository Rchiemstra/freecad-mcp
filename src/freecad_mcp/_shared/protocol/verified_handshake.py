"""Extracted ``VerifiedHandshake`` for ARCH002 (workstream 1G)."""

from __future__ import annotations

from dataclasses import dataclass

from .mcp_runtime_identity import McpRuntimeIdentity


@dataclass(frozen=True)
class VerifiedHandshake:
    client_nonce: str
    mcp: McpRuntimeIdentity
    requested_features: tuple[str, ...]
    required_features: tuple[str, ...]
