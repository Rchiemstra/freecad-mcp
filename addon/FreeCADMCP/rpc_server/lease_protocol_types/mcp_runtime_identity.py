"""Compatibility import for the canonical MCP runtime identity."""

try:
    from ..._shared.protocol.mcp_runtime_identity import McpRuntimeIdentity
except ImportError:
    from _shared.protocol.mcp_runtime_identity import McpRuntimeIdentity

__all__ = ["McpRuntimeIdentity"]
