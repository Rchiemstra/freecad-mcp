"""C1C public MCP outcomes for GUI timeout, transport loss, and request control."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.json_rpc_client import JsonRpcRemoteError
from freecad_mcp.generated.capabilities.register_modules import tools_runtime_control
from freecad_mcp.operations.parametric_ops import (
    set_expression,
    sketch_add_constraint,
    sketch_create,
)
from freecad_mcp.operations.parametric_ops.spreadsheet_set_cells import (
    spreadsheet_set_cells_operation,
)
from freecad_mcp.outcomes import status_from_error_code
from freecad_mcp.outcomes_types.outcome_status import OutcomeStatus
from freecad_mcp.responses import json_response, tool_fail

pytestmark = pytest.mark.unit

_REQUEST_ID = "11111111-2222-4333-8444-555555555555"


def _envelope(raw: dict) -> dict:
    return {
        "success": False,
        "request_id": _REQUEST_ID,
        **raw,
    }


def _assert_timeout_envelope(response, *, code: str, uncertain: bool, retry_safe: bool) -> None:
    envelope = response.structuredContent
    assert envelope["status"] in {"timed_out", "unknown"}
    assert envelope["status"] != "failed"
    assert envelope["correlation"]["request_id"] == _REQUEST_ID
    data = envelope["data"]
    assert data["error_code"] == code
    assert data["completion_uncertain"] is uncertain
    assert data.get("retry_safe") is retry_safe
    assert data.get("mutation_started") is False


def test_before_execution_sketch_create_reports_timed_out_not_failed() -> None:
    raw = _envelope(
        {
            "error_code": "GUI_TIMEOUT_BEFORE_EXECUTION",
            "timeout_stage": "before_execution",
            "error": "Timed out before execution",
            "completion_uncertain": True,
            "mutation_started": False,
        }
    )
    response = sketch_create.sketch_create_operation(
        SimpleNamespace(sketch_create=lambda *_a, **_k: raw),
        True,
        "Doc",
        "Sketch",
    )
    _assert_timeout_envelope(
        response,
        code="GUI_TIMEOUT_BEFORE_EXECUTION",
        uncertain=False,
        retry_safe=True,
    )


def test_during_execution_set_expression_reports_timed_out_not_failed() -> None:
    raw = _envelope(
        {
            "error_code": "GUI_TIMEOUT_DURING_EXECUTION",
            "timeout_stage": "during_execution",
            "error": "Timed out during execution",
            "completion_uncertain": True,
            "mutation_started": True,
            "execution_started": True,
        }
    )
    response = set_expression.set_expression_operation(
        SimpleNamespace(set_expression=lambda *_a, **_k: raw),
        True,
        "Doc",
        "Box",
        "Box.Length",
        "10 mm",
    )
    envelope = response.structuredContent
    assert envelope["status"] in {"timed_out", "unknown"}
    assert envelope["status"] != "failed"
    assert envelope["correlation"]["request_id"] == _REQUEST_ID
    data = envelope["data"]
    assert data["error_code"] == "GUI_TIMEOUT_DURING_EXECUTION"
    assert data["completion_uncertain"] is True
    assert data.get("retry_safe") is False


def test_during_execution_sketch_add_constraint_not_failed() -> None:
    raw = _envelope(
        {
            "error_code": "GUI_TIMEOUT_DURING_EXECUTION",
            "timeout_stage": "during_execution",
            "error": "Timed out during execution",
            "completion_uncertain": True,
            "mutation_started": True,
        }
    )
    response = sketch_add_constraint.sketch_add_constraint_operation(
        SimpleNamespace(sketch_add_constraint=lambda *_a, **_k: raw),
        True,
        "Doc",
        "Sketch",
        [],
    )
    assert response.structuredContent["status"] != "failed"
    assert response.structuredContent["correlation"]["request_id"] == _REQUEST_ID


def test_transport_uncertain_maps_to_unknown_not_failed() -> None:
    class _Conn:
        def set_expression(self, *_args, **_kwargs):
            raise TimeoutError("response lost after request was sent")

    response = set_expression.set_expression_operation(
        _Conn(), True, "Doc", "Box", "Box.Length", "10 mm"
    )
    envelope = response.structuredContent
    assert envelope["status"] == "unknown"
    assert envelope["status"] != "failed"
    assert envelope["data"]["error_code"] == "SET_EXPRESSION_TRANSPORT_UNCERTAIN"
    assert envelope["layers"]["transport_status"] != "succeeded"
    assert "GUI_TIMEOUT" not in str(envelope["data"]["error_code"])


def test_status_from_error_code_maps_uncertain_transport_to_unknown() -> None:
    assert status_from_error_code("SET_EXPRESSION_TRANSPORT_UNCERTAIN") == OutcomeStatus.UNKNOWN
    assert status_from_error_code("GUI_TIMEOUT_DURING_EXECUTION") == OutcomeStatus.TIMED_OUT


def test_get_request_status_running_after_timeout_is_not_succeeded() -> None:
    payload = {
        "success": True,
        "state": "running_after_timeout",
        "completion_uncertain": True,
        "request_id": _REQUEST_ID,
    }
    result = json_response(
        payload,
        status=tools_runtime_control.map_request_status_outcome(payload),
    )
    envelope = result.structuredContent
    assert envelope["status"] in {"timed_out", "unknown"}
    assert envelope["status"] != "succeeded"


def test_get_request_status_completed_with_late_completion_is_succeeded() -> None:
    payload = {
        "success": True,
        "state": "completed",
        "late_completion_available": True,
        "request_id": _REQUEST_ID,
    }
    result = json_response(
        payload,
        status=tools_runtime_control.map_request_status_outcome(payload),
    )
    assert result.structuredContent["status"] == "succeeded"


def test_cancel_after_mutation_started_real_finalize_payload_is_not_cancelled() -> None:
    """Live cancel_request payload from control_cancel_finalize (no inflight key)."""
    payload = {
        "success": True,
        "target_request_id": _REQUEST_ID,
        "cancellation": {
            "status": "completed",
            "request": {
                "request_id": _REQUEST_ID,
                "method": "set_expression",
                "phase": "cancelled_after_gui_phase",
                "cancellation_requested": True,
                "mutation_started": True,
                "uncertain": False,
                "handler_finished": False,
                "active_gui_phases": 0,
                "terminal": False,
                "terminal_status": None,
                "cancellation_resolved": False,
                "recovery_incident_id": None,
            },
        },
        "gui_queue": "not_queued",
    }
    status, error_code = tools_runtime_control.map_cancel_request_outcome(payload)
    assert status != OutcomeStatus.CANCELLED
    assert error_code == "REQUEST_CANCELLED_AFTER_MUTATION"


def test_cancel_after_mutation_started_is_not_succeeded() -> None:
    payload = {
        "success": True,
        "target_request_id": _REQUEST_ID,
        "gui_queue": "running",
        "cancellation": {
            "status": "requested",
            "request": {
                "request_id": _REQUEST_ID,
                "mutation_started": True,
                "uncertain": False,
            },
        },
    }
    _status, error_code = tools_runtime_control.map_cancel_request_outcome(payload)
    assert error_code == "REQUEST_CANCELLED_AFTER_MUTATION"
    payload["rolled_back"] = False
    result = tool_fail(
        "Cancellation recorded",
        structured=payload,
        error_code=error_code,
        status=OutcomeStatus.UNKNOWN,
    )
    envelope = result.structuredContent
    assert envelope["status"] in {"unknown", "cancelled"}
    assert envelope["status"] != "succeeded"
    assert envelope["data"].get("rolled_back") is False
    assert envelope["error_code"] == "REQUEST_CANCELLED_AFTER_MUTATION"


def test_queued_cancel_does_not_claim_rollback() -> None:
    payload = {
        "success": True,
        "target_request_id": _REQUEST_ID,
        "gui_queue": "cancelled_pending",
        "cancellation": {
            "status": "requested",
            "request": {
                "request_id": _REQUEST_ID,
                "mutation_started": False,
                "uncertain": False,
            },
        },
    }
    status, error_code = tools_runtime_control.map_cancel_request_outcome(payload)
    assert error_code is None
    result = json_response(payload, status=status)
    envelope = result.structuredContent
    assert envelope["status"] == "cancelled"
    assert envelope.get("rolled_back") is not True
    assert envelope["data"].get("rolled_back") is not True


def test_get_request_status_without_auth_reports_authentication_required() -> None:
    payload = {
        "success": False,
        "error": "Request status requires authentication",
        "error_code": "RPC_AUTHENTICATION_REQUIRED",
    }
    result = tool_fail(
        payload["error"],
        structured=payload,
        error_code=payload["error_code"],
        status=OutcomeStatus.UNKNOWN,
    )
    envelope = result.structuredContent
    assert envelope["error_code"] == "RPC_AUTHENTICATION_REQUIRED"
    assert envelope["status"] != "succeeded"


def test_get_request_status_unknown_uuid_reports_not_found() -> None:
    payload = {
        "success": False,
        "error": "Request not found",
        "error_code": "REQUEST_NOT_FOUND",
    }
    result = tool_fail(
        payload["error"],
        structured=payload,
        error_code=payload["error_code"],
        status=OutcomeStatus.UNKNOWN,
    )
    envelope = result.structuredContent
    assert envelope["error_code"] == "REQUEST_NOT_FOUND"


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


def test_lifted_json_rpc_gui_timeout_reports_timed_out_not_transport_uncertain() -> None:
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
    data = envelope["data"]
    assert data["error_code"] == "GUI_TIMEOUT_DURING_EXECUTION"
    assert data["error_code"] != "SPREADSHEET_SET_CELLS_TRANSPORT_UNCERTAIN"
    assert envelope["layers"]["transport_status"] == "succeeded"
    assert data["completion_uncertain"] is True
    assert data.get("retry_safe") is False


def test_dispatcher_timeout_not_parsed_as_invalid_contract() -> None:
    raw = _envelope(
        {
            "error_code": "GUI_TIMEOUT_DURING_EXECUTION",
            "timeout_stage": "during_execution",
            "error": "Timed out",
            "completion_uncertain": True,
        }
    )
    response = sketch_create.sketch_create_operation(
        SimpleNamespace(sketch_create=lambda *_a, **_k: raw),
        True,
        "Doc",
        "Sketch",
    )
    assert response.structuredContent["data"]["error_code"] == "GUI_TIMEOUT_DURING_EXECUTION"
    assert "INVALID_" not in str(response.structuredContent["data"].get("error_code"))
