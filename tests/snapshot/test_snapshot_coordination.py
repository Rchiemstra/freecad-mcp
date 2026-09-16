"""Snapshot retry behavior at the RPC/GUI boundary."""

from __future__ import annotations

import importlib
from pathlib import Path

import FreeCADGui

if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server import rpc_server, snapshot_service

_snapshot_save_context = importlib.import_module(
    "addon.FreeCADMCP.rpc_server.snapshot_service_ops.snapshot_save_context"
)


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


def test_worker_snapshot_uses_native_authority_neutral_context(tmp_path, monkeypatch):
    manager = _Manager(tmp_path)
    monkeypatch.setattr(rpc_server, "worker_manager", manager)
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
    assert captured[0][3:] == ({}, "", ())


def test_snapshot_save_copy_does_not_open_legacy_authority(tmp_path, monkeypatch):
    callback_calls = []

    class Document:
        Name = "Model"
        Label = "Model"
        Uid = "uid"
        Id = 1
        FileName = ""
        Modified = True
        Objects = ()
        HasPendingTransaction = False
        Transacting = False
        LastModifiedDate = ""

        @staticmethod
        def getDependentDocuments():
            return []

        @staticmethod
        def saveCopy(path):
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

    def retired_callback(*args, **kwargs):
        callback_calls.append((args, kwargs))

    _snapshot_save_context.bind_snapshot_save_context(
        _snapshot_save_context.SnapshotSaveBindings(
            begin_agent_mutation_scope=retired_callback,
            end_agent_mutation_scope=retired_callback,
            begin_internal_snapshot_save_scope=retired_callback,
            end_internal_snapshot_save_scope=retired_callback,
            open_documents_mutation_capability=retired_callback,
        )
    )

    result = snapshot_service.create_snapshot_bundle_gui(
        "Model",
        str(tmp_path),
        mutation_generations={"Model": 7},
        mutation_request_id="11111111-1111-4111-8111-111111111111",
        mutation_document_keys=("Model",),
    )

    assert result["ok"] is True
    assert callback_calls == []
    assert Path(result["documents"][0]["snapshot_path"]).read_bytes() == b"snapshot"


def test_snapshot_observer_scope_is_state_free(tmp_path, monkeypatch):
    observations = []

    class Document:
        Name = "Model"
        Label = "Model"
        Uid = "uid"
        Id = 1
        FileName = ""
        Modified = False
        Objects = ()
        HasPendingTransaction = False
        Transacting = False
        LastModifiedDate = ""

        @staticmethod
        def getDependentDocuments():
            return []

        @staticmethod
        def saveCopy(path):
            observations.append(Path(path))
            Path(path).write_bytes(b"read-only snapshot")

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
    result = snapshot_service.create_snapshot_bundle_gui(
        "Model",
        str(tmp_path),
        mutation_generations={},
        mutation_request_id="22222222-2222-4222-8222-222222222222",
        mutation_document_keys=(),
    )

    assert result["ok"] is True
    target = Path(result["documents"][0]["snapshot_path"])
    assert target.read_bytes() == b"read-only snapshot"
    assert observations == [target]
    assert not hasattr(_snapshot_save_context, "_bindings")
