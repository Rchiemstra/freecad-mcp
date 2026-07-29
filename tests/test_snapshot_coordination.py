"""Snapshot retry behavior at the RPC/GUI boundary."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import FreeCADGui


if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.document_lease import core_authority
from addon.FreeCADMCP import document_lock
from addon.FreeCADMCP.rpc_server import rpc_server
from addon.FreeCADMCP.rpc_server import snapshot_service


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


def test_worker_snapshot_receives_only_callers_lease_generations(
    tmp_path, monkeypatch
):
    manager = _Manager(tmp_path)
    monkeypatch.setattr(rpc_server, "worker_manager", manager)
    monkeypatch.setattr(
        rpc_server,
        "document_lease_service",
        SimpleNamespace(
            list_records=lambda: [
                {
                    "generation": 7,
                    "owner": {"mcp_instance_id": "runtime-a"},
                    "document": {
                        "name": "Model",
                        "session_uuid": "model-session",
                        "canonical_path": "C:/models/Model.FCStd",
                        "comparison_key": "c:/models/model.fcstd",
                    },
                },
                {
                    "generation": 11,
                    "owner": {"mcp_instance_id": "runtime-b"},
                    "document": {"name": "Foreign"},
                },
            ]
        ),
    )
    monkeypatch.setattr(
        rpc_server,
        "_import_document_lock",
        lambda: SimpleNamespace(
            get_request_identity=lambda: {
                "instance_id": "runtime-a",
                "request_id": "request-123",
            }
        ),
    )
    captured = []

    def create_snapshot(
        document_name,
        workspace,
        link_policy="strict",
        mutation_generations=None,
        mutation_request_id="",
        mutation_document_keys=(),
    ):
        captured.append(
            (
                document_name,
                workspace,
                link_policy,
                mutation_generations,
                mutation_request_id,
                mutation_document_keys,
            )
        )
        return {"ok": True, "documents": [{"document_name": document_name}]}

    monkeypatch.setattr(rpc_server, "create_primary_snapshot_gui", create_snapshot)
    rpc = rpc_server.FreeCADRPC()
    monkeypatch.setattr(rpc, "_dispatch_snapshot_gui", lambda task: task())

    result = rpc._execute_code_worker("print(1)", {"document": "Model"})

    assert result["success"] is True
    assert captured[0][0] == "Model"
    assert captured[0][3] == {"Model": 7}
    assert captured[0][4] == "request-123"
    assert captured[0][5] == (
        "C:/models/Model.FCStd",
        "Model",
        "c:/models/model.fcstd",
        "model-session",
    )


def test_snapshot_save_copy_runs_inside_generation_scoped_capability(
    tmp_path, monkeypatch
):
    capability_active = False
    capability_calls = []
    request_id = "11111111-1111-4111-8111-111111111111"

    class Document:
        Name = "Model"
        Label = "Model"
        Uid = "uid"
        Id = 1
        FileName = ""
        Modified = True
        Objects = []
        HasPendingTransaction = False
        Transacting = False
        LastModifiedDate = ""

        @staticmethod
        def getDependentDocuments():
            return []

        @staticmethod
        def saveCopy(path):
            assert capability_active is True
            assert document_lock.is_agent_mutating(
                "Model", request_id=request_id
            )
            Path(path).write_bytes(b"snapshot")

    document = Document()
    monkeypatch.setattr(
        snapshot_service.FreeCAD,
        "getDocument",
        lambda name: document if name == "Model" else None,
    )
    monkeypatch.setattr(
        snapshot_service.FreeCAD,
        "listDocuments",
        lambda: {"Model": document},
    )
    monkeypatch.setattr(
        snapshot_service.FreeCAD,
        "ActiveDocument",
        document,
        raising=False,
    )

    @contextmanager
    def capability(documents, *, generations, kinds):
        nonlocal capability_active
        capability_calls.append((documents, generations, kinds))
        capability_active = True
        try:
            yield [object()]
        finally:
            capability_active = False

    monkeypatch.setattr(
        core_authority,
        "open_documents_mutation_capability",
        capability,
    )

    result = snapshot_service.create_snapshot_bundle_gui(
        "Model",
        str(tmp_path),
        mutation_generations={"Model": 7},
        mutation_request_id=request_id,
        mutation_document_keys=("Model",),
    )

    assert result["ok"] is True
    assert capability_calls == [([document], {"Model": 7}, ("SaveAs",))]
    assert not document_lock.is_agent_mutating("Model", request_id=request_id)
    assert Path(result["documents"][0]["snapshot_path"]).read_bytes() == b"snapshot"
