"""Adversarial wire cases for the ``spreadsheet_set_cells`` contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.json_rpc_client import JsonRpcRemoteError
from freecad_mcp._shared.protocol.spreadsheet_set_cells_contract import (
    make_spreadsheet_set_cells_success,
    parse_spreadsheet_set_cells_response,
)
from freecad_mcp.operations.parametric_ops.spreadsheet_set_cells import (
    spreadsheet_set_cells_operation,
)


def _success():
    return make_spreadsheet_set_cells_success(sheet="Value")


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_spreadsheet_set_cells_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize("version", [None, True, False, 1.0, "1", 0, 2])
def test_contract_version_must_be_the_exact_integer(version):
    assert parse_spreadsheet_set_cells_response(dict(_success(), contract_version=version))["success"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"rollback_failed": True},
        {"rollback_succeeded": True},
        {"native_status": "Rejected"},
        {"success": 1},
        {"ok": 1},
        {"committed": 1},
        {"retry_safe": 0},
        {"completion_uncertain": True},
    ],
)
def test_contradictory_or_malformed_success_cannot_escape(change):
    result = parse_spreadsheet_set_cells_response(dict(_success(), **change))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_spreadsheet_set_cells_response(raw) == raw


_REQUEST_ID = "11111111-2222-4333-8444-555555555555"


def test_gui_timeout_during_execution_reports_timed_out_not_failed():
    raw = {
        "success": False,
        "request_id": _REQUEST_ID,
        "error_code": "GUI_TIMEOUT_DURING_EXECUTION",
        "timeout_stage": "during_execution",
        "error": "Timed out during execution",
        "completion_uncertain": True,
        "mutation_started": True,
    }
    response = spreadsheet_set_cells_operation(
        SimpleNamespace(spreadsheet_set_cells=lambda *_a, **_k: raw),
        True,
        "Doc",
        "Value",
        [{"address": "A1", "value": 1}],
    )
    envelope = response.structuredContent
    assert envelope["status"] in {"timed_out", "unknown"}
    assert envelope["status"] != "failed"
    assert envelope["correlation"]["request_id"] == _REQUEST_ID
    assert envelope["data"]["error_code"] == "GUI_TIMEOUT_DURING_EXECUTION"


def test_transport_failure_preserves_unknown_model_state():
    class _Conn:
        def spreadsheet_set_cells(self, *args, **kwargs):
            raise TimeoutError("response lost after request was sent")

    response = spreadsheet_set_cells_operation(_Conn(), True, "Doc", "Value", [{"address": "A1", "value": 1}])
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "SPREADSHEET_SET_CELLS_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


_GUI_TIMEOUT_MESSAGE = (
    "Timed out after 30.0s waiting for FreeCAD GUI response while executing; "
    "execution continues in FreeCAD and may keep the GUI unresponsive. "
    "New GUI work is rejected until the request finishes"
)


def _lifted_gui_timeout_remote_error() -> JsonRpcRemoteError:
    return JsonRpcRemoteError(
        -32000,
        _GUI_TIMEOUT_MESSAGE,
        data={
            "request_id": _REQUEST_ID,
            "error_code": "GUI_TIMEOUT_DURING_EXECUTION",
            "timeout_stage": "during_execution",
            "completion_uncertain": True,
            "execution_started": True,
            "mutation_started": True,
        },
        request_id=_REQUEST_ID,
    )


def test_lifted_json_rpc_gui_timeout_reports_timed_out_not_transport_uncertain():
    remote_error = _lifted_gui_timeout_remote_error()

    class _Conn:
        def spreadsheet_set_cells(self, *_args, **_kwargs):
            raise remote_error

    response = spreadsheet_set_cells_operation(
        _Conn(),
        True,
        "Doc",
        "Value",
        [{"address": "A1", "value": 1}],
    )
    envelope = response.structuredContent
    assert envelope["status"] == "timed_out"
    assert envelope["status"] != "failed"
    assert envelope["correlation"]["request_id"] == _REQUEST_ID
    assert envelope["data"]["error_code"] == "GUI_TIMEOUT_DURING_EXECUTION"
    assert envelope["layers"]["transport_status"] == "succeeded"
    assert envelope["data"]["error_code"] != "SPREADSHEET_SET_CELLS_TRANSPORT_UNCERTAIN"
