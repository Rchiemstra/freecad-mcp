"""Process-tree cleanup tests for the instrumented MCP launcher (R2)."""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from freecad_mcp import process_tree
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


@pytest.mark.unit
def test_windows_liveness_probe_never_uses_os_kill(monkeypatch):
    monkeypatch.setattr(process_tree.sys, "platform", "win32")
    monkeypatch.setattr(
        process_tree.os,
        "kill",
        lambda *_args: pytest.fail("Windows liveness must never call os.kill"),
    )

    # On non-Windows hosts ctypes.WinDLL is unavailable; unknown must be
    # preserved as alive without falling back to destructive signal emulation.
    assert isinstance(process_tree._pid_alive(4242), bool)
