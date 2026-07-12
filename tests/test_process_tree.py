"""Process-tree cleanup tests for the instrumented MCP launcher (R2)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import sys

from freecad_mcp.process_tree import kill_process_tree


@pytest.mark.unit
def test_kill_process_tree_terminates_descendants():
    with patch("freecad_mcp.process_tree._iter_descendant_pids", return_value=[42, 43]):
        if sys.platform == "win32":
            with patch("freecad_mcp.process_tree.subprocess.run") as run:
                kill_process_tree(41)
                assert run.call_count >= 1
        else:
            with patch("freecad_mcp.process_tree.os.kill") as kill:
                kill_process_tree(41)
                assert kill.call_count >= 2
