"""GUI execute_code post-mutation flush coverage."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task import (
    run_execute_code_gui_task,
)

pytestmark = pytest.mark.unit


def test_mutating_execute_flushes_gui_events_after_success(monkeypatch):
    flushed = []
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task._flush_gui_events",
        lambda: flushed.append(True),
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.run_python_on_gui_thread",
        lambda code, output, freecad=None: (True, None),
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.restore_save_hooks",
        lambda hooks: None,
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.recompute_documents",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.restore_active_document",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.build_execute_session",
        lambda **_kwargs: {"documents": []},
    )

    freecad = SimpleNamespace(
        ActiveDocument=None,
        listDocuments=lambda: {},
        setActiveDocument=MagicMock(),
        getDocument=MagicMock(side_effect=NameError("Unknown document")),
    )

    result = run_execute_code_gui_task(
        "doc.addObject('Part::Feature', 'Box')",
        {"read_only": False},
        freecad=freecad,
        collect_invalid_objects_fn=lambda: [],
    )

    assert result["ok"] is True
    assert flushed == [True]


def test_read_only_execute_skips_gui_flush(monkeypatch):
    flushed = []
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task._flush_gui_events",
        lambda: flushed.append(True),
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.run_python_on_gui_thread",
        lambda code, output, freecad=None: (True, None),
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.install_read_only_save_hooks",
        lambda **_kwargs: ([], []),
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.restore_save_hooks",
        lambda hooks: None,
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.recompute_documents",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.restore_active_document",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.build_execute_session",
        lambda **_kwargs: {"documents": []},
    )

    freecad = SimpleNamespace(
        ActiveDocument=None,
        listDocuments=lambda: {},
    )

    result = run_execute_code_gui_task(
        "print(1)",
        {"read_only": True},
        freecad=freecad,
        collect_invalid_objects_fn=lambda: [],
    )

    assert result["ok"] is True
    assert flushed == []


def test_native_boundary_defers_recompute_session_and_flush_to_owned_phases(
    monkeypatch,
):
    events = []
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task._flush_gui_events",
        lambda: events.append("flush"),
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.run_python_on_gui_thread",
        lambda code, output, freecad=None: (events.append("apply") or True, None),
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.restore_save_hooks",
        lambda hooks: None,
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.recompute_documents",
        lambda *_args, **_kwargs: events.append("adapter-recompute"),
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.restore_active_document",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task.build_execute_session",
        lambda **_kwargs: events.append("postcondition-session") or {"documents": []},
    )
    freecad = SimpleNamespace(
        ActiveDocument=None,
        listDocuments=lambda: {},
        setActiveDocument=MagicMock(),
        getDocument=MagicMock(side_effect=NameError("Unknown document")),
    )
    postcondition_sink = {}

    provisional = run_execute_code_gui_task(
        "print(1)",
        {"read_only": False, "recompute": "target", "document": "Model"},
        freecad=freecad,
        collect_invalid_objects_fn=lambda: [],
        native_boundary=True,
        postcondition_sink=postcondition_sink,
    )

    assert provisional == {"ok": True, "session": {}, "stdout": ""}
    assert events == ["apply"]
    finalized = postcondition_sink["finalize"]()
    assert finalized["ok"] is True
    assert finalized["session"] == {"documents": []}
    assert events == ["apply", "postcondition-session"]
