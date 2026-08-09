"""Snapshot retry behavior at the RPC/GUI boundary."""

from __future__ import annotations

from pathlib import Path

import FreeCADGui


if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server import rpc_server


class _Manager:
    def __init__(self, root: Path):
        self.root = root
        self.executions = 0

    def create_workspace(self):
        workspace = self.root / "workspace"
        workspace.mkdir(exist_ok=True)
        return workspace

    def execute(self, code, options, snapshot, workspace):
        self.executions += 1
        return {"success": True, "snapshot": snapshot}


def test_snapshot_state_changes_once_then_retry_succeeds(tmp_path, monkeypatch):
    manager = _Manager(tmp_path)
    monkeypatch.setattr(rpc_server, "worker_manager", manager)
    outcomes = iter([
        {"ok": False, "error_code": "snapshot_state_changed", "error": "changed"},
        {"ok": True, "documents": [{"document_name": "Model"}]},
    ])
    rpc = rpc_server.FreeCADRPC()
    monkeypatch.setattr(rpc, "_dispatch_snapshot_gui", lambda _task: next(outcomes))
    result = rpc._execute_code_worker("print(1)", {"document": "Model"})
    assert result["success"] is True
    assert manager.executions == 1


def test_snapshot_state_changes_twice_returns_structured_error(tmp_path, monkeypatch):
    manager = _Manager(tmp_path)
    monkeypatch.setattr(rpc_server, "worker_manager", manager)
    calls = []
    rpc = rpc_server.FreeCADRPC()
    monkeypatch.setattr(
        rpc,
        "_dispatch_snapshot_gui",
        lambda _task: calls.append(True) or {
            "ok": False,
            "error_code": "snapshot_state_changed",
            "error": "changed twice",
        },
    )
    result = rpc._execute_code_worker("print(1)", {"document": "Model"})
    assert result["success"] is False
    assert result["error_code"] == "snapshot_state_changed"
    assert len(calls) == 2
    assert manager.executions == 0
