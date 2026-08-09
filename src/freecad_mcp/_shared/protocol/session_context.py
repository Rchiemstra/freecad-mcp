"""Extracted ``SessionContext`` for ARCH002 (workstream 1G)."""

from __future__ import annotations

from dataclasses import dataclass

from .mcp_runtime_identity import McpRuntimeIdentity


@dataclass(frozen=True)
class SessionContext:
    session_id: str
    mcp: McpRuntimeIdentity
    negotiated_features: tuple[str, ...]
    issued_at: str
    expires_at: str
