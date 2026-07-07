"""P12 / I7: reliable snapshots / restore for agent experimentation.

Because several FreeCAD behaviours are silent and destructive, agents need
cheap, automatic document snapshots + restore so a bad step is one call to
undo. The MCP exposes `snapshot` and `restore` tools backed by
`snapshot_operation` / `restore_operation` (implemented in I7).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_snapshot_and_restore_operations_exist():
    import freecad_mcp.operations as ops
    assert hasattr(ops, "snapshot_operation"), "freecad_mcp.operations should expose snapshot_operation (I7)"
    assert hasattr(ops, "restore_operation"), "freecad_mcp.operations should expose restore_operation (I7)"
