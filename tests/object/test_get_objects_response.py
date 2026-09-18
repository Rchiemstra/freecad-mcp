"""Adversarial wire cases for the get_objects contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.get_objects_contract import (
    GET_OBJECTS_CONTRACT_VERSION,
    make_get_objects_failure,
    make_get_objects_success,
    parse_get_objects_response,
)
from freecad_mcp._shared.protocol.json_rpc_client import JsonRpcRemoteError
from freecad_mcp.operations.core_ops.object_ops import get_objects_operation


def _success():
    return make_get_objects_success(
        doc_name="Doc",
        objects=[{"Name": "Box", "Label": "Box", "TypeId": "Part::Feature"}],
        total_count=1,
        returned_count=1,
        page_size=50,
        complete=True,
        next_cursor=None,
        snapshot_id="abc123",
    )


@pytest.mark.parametrize("raw", [None, 1, {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_get_objects_response(raw)
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
def test_timeout_string_stays_timed_out_not_empty_list(raw):
    result = parse_get_objects_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["error_code"] == "GUI_TIMEOUT_DURING_EXECUTION"


def test_retired_bare_list_stays_invalid():
    result = parse_get_objects_response([{"Name": "Box"}])
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["error_code"] == "INVALID_RPC_RESPONSE"


def test_gui_dispatch_timeout_dict_stays_timed_out():
    raw = {
        "success": False,
        "error_code": "GUI_TIMEOUT_BEFORE_EXECUTION",
        "error": (
            "Timed out after 30s waiting for FreeCAD GUI response before execution"
        ),
    }
    result = parse_get_objects_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["error_code"] == "GUI_TIMEOUT_BEFORE_EXECUTION"


def test_valid_success_round_trips():
    raw = _success()
    assert parse_get_objects_response(raw) == raw


def _connection(get_objects):
    return SimpleNamespace(get_objects=get_objects, get_active_screenshot=lambda: None)


def test_json_rpc_remote_document_not_found_surfaces_proven_rejection():
    def raises_remote(*_args, **_kwargs):
        raise JsonRpcRemoteError(
            -32000,
            "Document not found: 'MissingDoc'",
            data={
                "contract_version": GET_OBJECTS_CONTRACT_VERSION,
                "success": False,
                "ok": False,
                "outcome": "rejected",
                "committed": False,
                "retry_safe": True,
                "error_code": "DOCUMENT_NOT_FOUND",
                "error": "Document not found: 'MissingDoc'",
            },
        )

    response = get_objects_operation(_connection(raises_remote), True, "MissingDoc")
    assert response.isError is True
    envelope = response.structuredContent
    data = envelope["data"]
    assert data["error_code"] == "DOCUMENT_NOT_FOUND"
    assert data["outcome"] == "rejected"
    assert envelope["status"] == "failed"


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = get_objects_operation(
        SimpleNamespace(get_objects=lost_response, get_active_screenshot=lambda: None),
        True,
        "Doc",
    )
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "GET_OBJECTS_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_missing_document_never_succeeds_with_empty_list():
    def missing_document(*_args, **_kwargs):
        return make_get_objects_failure(
            "DOCUMENT_NOT_FOUND",
            "Document not found: 'Doc'",
        )

    conn = SimpleNamespace(
        get_objects=missing_document,
        get_active_screenshot=lambda: None,
    )
    response = get_objects_operation(
        conn,
        True,
        "Doc",
    )
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "DOCUMENT_NOT_FOUND"
    assert data["success"] is False
