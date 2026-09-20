"""Adversarial wire cases for the get_object contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.get_object_contract import (
    GET_OBJECT_CONTRACT_VERSION,
    make_get_object_failure,
    make_get_object_success,
    parse_get_object_response,
)
from freecad_mcp._shared.protocol.json_rpc_client import JsonRpcRemoteError
from freecad_mcp.operations.core_ops.object_ops import get_object_operation


def _success():
    return make_get_object_success(
        object="Box",
        object_data={"Name": "Box", "Label": "Box", "TypeId": "Part::Feature"},
    )


@pytest.mark.parametrize("raw", [None, [], 1, {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_get_object_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


@pytest.mark.parametrize(
    "raw",
    [
        "timeout",
        "Timed out after 30s waiting for FreeCAD GUI response while executing",
    ],
)
def test_timeout_string_stays_timed_out_not_object_not_found(raw):
    result = parse_get_object_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["error_code"] == "GUI_TIMEOUT_DURING_EXECUTION"


def test_gui_dispatch_timeout_dict_stays_timed_out():
    raw = {
        "success": False,
        "error_code": "GUI_TIMEOUT_BEFORE_EXECUTION",
        "error": "Timed out after 30s waiting for FreeCAD GUI response before execution",
    }
    result = parse_get_object_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["error_code"] == "GUI_TIMEOUT_BEFORE_EXECUTION"


def test_valid_success_round_trips():
    raw = _success()
    assert parse_get_object_response(raw) == raw


def _connection(get_object):
    return SimpleNamespace(get_object=get_object, get_active_screenshot=lambda: None)


def test_json_rpc_remote_object_not_found_surfaces_proven_rejection():
    def raises_remote(*_args, **_kwargs):
        raise JsonRpcRemoteError(
            -32000,
            "Object not found",
            data={
                "success": False,
                "ok": False,
                "error_code": "OBJECT_NOT_FOUND",
                "error": "Object not found",
            },
        )

    response = get_object_operation(_connection(raises_remote), True, "Doc", "Missing")
    assert response.isError is True
    envelope = response.structuredContent
    data = envelope["data"]
    assert data["error_code"] == "OBJECT_NOT_FOUND"
    assert data["outcome"] == "rejected"
    assert envelope["status"] == "failed"
    assert envelope["layers"]["tool_status"] == "failed"


def test_json_rpc_remote_document_not_found_surfaces_proven_rejection():
    def raises_remote(*_args, **_kwargs):
        raise JsonRpcRemoteError(
            -32000,
            "Document not found: 'MissingDoc'",
            data={
                "contract_version": GET_OBJECT_CONTRACT_VERSION,
                "success": False,
                "ok": False,
                "outcome": "rejected",
                "committed": False,
                "retry_safe": True,
                "error_code": "DOCUMENT_NOT_FOUND",
                "error": "Document not found: 'MissingDoc'",
            },
        )

    response = get_object_operation(_connection(raises_remote), True, "MissingDoc", "Box")
    assert response.isError is True
    envelope = response.structuredContent
    data = envelope["data"]
    assert data["error_code"] == "DOCUMENT_NOT_FOUND"
    assert data["outcome"] == "rejected"
    assert envelope["status"] == "failed"
    assert envelope["layers"]["tool_status"] == "failed"


def test_missing_object_never_succeeds_with_null():
    def missing_object(*_args, **_kwargs):
        return make_get_object_failure("OBJECT_NOT_FOUND", "Object not found")

    response = get_object_operation(
        SimpleNamespace(get_object=missing_object, get_active_screenshot=lambda: None),
        True,
        "Doc",
        "Missing",
    )
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "OBJECT_NOT_FOUND"
    assert data["success"] is False
    assert response.structuredContent["status"] == "failed"


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = get_object_operation(
        SimpleNamespace(get_object=lost_response, get_active_screenshot=lambda: None),
        True,
        "Doc",
        "Box",
    )
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "GET_OBJECT_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_get_object_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
