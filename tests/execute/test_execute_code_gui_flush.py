"""GUI execute_code post-mutation flush coverage."""

from __future__ import annotations

import io
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
        getDocument=MagicMock(return_value=None),
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
