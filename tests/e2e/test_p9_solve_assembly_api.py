"""P9 / I9: `solve_assembly` is available.

`Assembly.solveAssembly` does not exist and the solve API is undocumented. The
MCP exposes a `solve_assembly` tool (backed by `solve_assembly_operation`) so
agents can re-solve after editing a joint or a referenced face. Implemented in
I9.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_solve_assembly_operation_exists():
    import freecad_mcp.operations as ops
    assert hasattr(ops, "solve_assembly_operation"), (
        "freecad_mcp.operations should expose solve_assembly_operation (I9)"
    )


def test_solve_assembly_tool_registered():
    # Importing server.py builds the FastMCP tool registry as a side effect.
    import freecad_mcp.server as server
    tools = getattr(server.mcp, "_tool_manager", None)
    tool_names = []
    if tools is not None:
        # FastMCP stores tools on the manager; fall back gracefully across versions.
        registry = getattr(tools, "_tools", None) or getattr(tools, "tools", None)
        if isinstance(registry, dict):
            tool_names = list(registry)
    assert "solve_assembly" in tool_names, (
        f"solve_assembly @mcp.tool not registered; got {tool_names[:0]}"
    )
