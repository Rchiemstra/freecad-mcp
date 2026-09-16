from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from addon.FreeCADMCP import automation_pause
from freecad_mcp.execute_options import ExecuteOptions
from tests import conftest as live_fixtures
from tests.conftest import (
    LiveFreeCADConnection,
    _InlineGuiDispatcher,
    _build_live_freecad_rpc,
)


def _connection_with_rpc():
    connection = object.__new__(LiveFreeCADConnection)
    connection.doc = SimpleNamespace(Name="Primary")
    connection._typed_rpc = MagicMock()
    connection._globals = {}
    return connection


@pytest.fixture(autouse=True)
def _reset_automation_pause():
    automation_pause._paused = False
    automation_pause._active.clear()
    automation_pause._last_finished = None
    yield
    automation_pause._paused = False
    automation_pause._active.clear()
    automation_pause._last_finished = None


def test_plain_python_stub_is_not_reported_as_live_freecad(monkeypatch):
    monkeypatch.setattr(
        live_fixtures,
        "FreeCAD",
        SimpleNamespace(__mcp_test_stub__=True),
    )

    assert live_fixtures._freecad_available() is False


def test_inline_gui_dispatcher_rejects_transport_context():
    from addon.FreeCADMCP.dispatch.gui_errors import GuiDispatchError

    dispatcher = _InlineGuiDispatcher()

    assert dispatcher.submit(lambda: "done", 1.0) == "done"
    with pytest.raises(GuiDispatchError, match="cannot emulate authenticated"):
        dispatcher.submit(lambda: None, 1.0, request_id="request")
    with pytest.raises(GuiDispatchError, match="cannot emulate authenticated"):
        dispatcher.submit(lambda: None, 1.0, on_complete=lambda _result: None)


def test_live_rpc_composition_is_isolated_and_has_no_fake_worker():
    rpc = _build_live_freecad_rpc()

    assert isinstance(rpc._execution_collaborators.gui_dispatcher, _InlineGuiDispatcher)
    assert rpc._execution_collaborators.worker_manager is None
    assert rpc._execution_collaborators.session_manager is None
    assert rpc._execution_collaborators.runtime_manifest is None
    assert rpc._execution_collaborators.actual_endpoint is None
    assert (
        rpc._execution_collaborators.compatibility_api
        is rpc._collaboration_collaborators.compatibility_api
    )


def test_mutating_execute_code_uses_production_rpc_and_primary_document():
    connection = _connection_with_rpc()
    connection._typed_rpc._dispatch.return_value = {"success": True}

    result = connection.execute_code("value = 1")

    assert result == {"success": True}
    connection._typed_rpc._dispatch.assert_called_once_with(
        "execute_code", ["value = 1", {"document": "Primary"}]
    )
    assert "value" not in connection._globals


def test_execute_options_are_normalized_before_mutating_rpc_call():
    connection = _connection_with_rpc()
    connection._typed_rpc._dispatch.return_value = {"success": True}
    options = ExecuteOptions(
        document="Other",
        affected_documents=["Other"],
        recompute="target",
        recompute_documents=["Other"],
        generated_operation=True,
        operation_id="test mutation",
    )

    connection.execute_code("pass", options)

    connection._typed_rpc._dispatch.assert_called_once_with(
        "execute_code", ["pass", options.to_dict()]
    )


def test_execute_options_without_document_use_fixture_document():
    connection = _connection_with_rpc()
    connection._typed_rpc._dispatch.return_value = {"success": True}
    options = ExecuteOptions(generated_operation=True, operation_id="test mutation")

    connection.execute_code("pass", options)

    expected = options.to_dict()
    expected["document"] = "Primary"
    connection._typed_rpc._dispatch.assert_called_once_with(
        "execute_code", ["pass", expected]
    )


def test_read_only_execute_code_stays_in_process_without_fake_worker():
    connection = _connection_with_rpc()

    result = connection.execute_code(
        "print('read probe')",
        ExecuteOptions(read_only=True, execution_mode="worker"),
    )

    assert result["success"] is True
    assert "read probe" in result["message"]
    connection._typed_rpc._dispatch.assert_not_called()


def test_typed_feature_history_and_readiness_methods_delegate_exactly():
    connection = _connection_with_rpc()
    connection._typed_rpc._dispatch.side_effect = [
        {"success": True},
        {"success": True},
        {"success": True},
        {"success": True},
        {"success": True, "ready": True},
    ]

    assert connection.pad_feature(
        "Doc", "Sketch", "Pad", 4.0, "Body", True, False, True
    ) == {"success": True}
    assert connection.pocket_feature(
        "Doc", "Inner", "Pocket", 2.0, "Body", False, True, True
    ) == {"success": True}
    assert connection.undo("Doc") == {"success": True}
    assert connection.redo("Doc") == {"success": True}
    assert connection.get_mutation_readiness("Doc") == {
        "success": True,
        "ready": True,
    }

    assert connection._typed_rpc._dispatch.call_args_list == [
        call(
            "pad_feature",
            ["Doc", "Sketch", "Pad", 4.0, "Body", True, False, True],
        ),
        call(
            "pocket_feature",
            ["Doc", "Inner", "Pocket", 2.0, "Body", False, True, True],
        ),
        call("undo", ["Doc"]),
        call("redo", ["Doc"]),
        call("get_mutation_readiness", ["Doc"]),
    ]


def test_generated_typed_mutation_methods_delegate_to_production_dispatch():
    connection = _connection_with_rpc()
    connection._typed_rpc._dispatch.return_value = {"success": True}

    assert connection.body_create("Doc", "Body") == {"success": True}
    assert connection.sketch_create("Doc", "Sketch", "Body", "XY_Plane") == {
        "success": True
    }
    assert connection.spreadsheet_create("Doc", "Dims") == {"success": True}
    assert connection.spreadsheet_set_cells(
        "Doc", "Dims", [{"address": "A1", "value": 3.0}]
    ) == {"success": True}

    assert connection._typed_rpc._dispatch.call_args_list == [
        call("body_create", ["Doc", "Body"]),
        call("sketch_create", ["Doc", "Sketch", "Body", "XY_Plane"]),
        call("spreadsheet_create", ["Doc", "Dims"]),
        call(
            "spreadsheet_set_cells",
            ["Doc", "Dims", [{"address": "A1", "value": 3.0}]],
        ),
    ]


def test_production_dispatch_refuses_live_fixture_mutations_while_paused():
    leaves = SimpleNamespace(
        execute_code=MagicMock(return_value={"success": True}),
        pad_feature=MagicMock(return_value={"success": True}),
        pocket_feature=MagicMock(return_value={"success": True}),
        undo=MagicMock(return_value={"success": True}),
        redo=MagicMock(return_value={"success": True}),
    )
    connection = _connection_with_rpc()
    connection._typed_rpc = leaves
    from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_core import (
        dispatch,
    )

    leaves._dispatch = lambda method, params: dispatch(leaves, method, params)
    automation_pause.request_local_pause_after_current()

    responses = [
        connection.execute_code("pass"),
        connection.pad_feature("Primary", "S", "Pad", 1.0),
        connection.pocket_feature("Primary", "S", "Pocket", 1.0),
        connection.undo("Primary"),
        connection.redo("Primary"),
    ]

    assert all(item.get("error_code") == "AUTOMATION_PAUSED" for item in responses)
    for name in ("execute_code", "pad_feature", "pocket_feature", "undo", "redo"):
        getattr(leaves, name).assert_not_called()


def test_execute_dispatch_reports_document_in_current_operation():
    from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_core import (
        dispatch,
    )

    observed = {}
    leaves = SimpleNamespace()

    def execute_code(_code, _options):
        observed.update(automation_pause.status())
        return {"success": True}

    leaves.execute_code = execute_code
    result = dispatch(
        leaves,
        "execute_code",
        ["pass", {"document": "Primary"}],
    )

    assert result == {"success": True}
    assert observed["current_operation"] == {
        "method": "execute_code",
        "documents": ("Primary",),
    }
