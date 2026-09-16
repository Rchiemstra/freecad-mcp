"""Focused JSON-RPC 2.0 transport and listener tests."""

from __future__ import annotations

import json
import logging

import pytest

from addon.FreeCADMCP.rpc_server.json_rpc_errors import json_rpc_error_from_result
from addon.FreeCADMCP.rpc_server.json_rpc_transport import (
    JsonRpcError,
    JsonRpcTransport,
)

pytestmark = pytest.mark.unit


def _decode(payload):
    assert payload is not None
    return json.loads(payload)


def test_request_routes_array_params_through_existing_dispatch_shape():
    calls = []
    transport = JsonRpcTransport(
        lambda method, params: calls.append((method, params)) or {"value": params[0]}
    )

    response = _decode(
        transport.handle_bytes(
            b'{"jsonrpc":"2.0","method":"echo","params":[null],"id":7}'
        )
    )

    assert calls == [("echo", (None,))]
    assert response == {"jsonrpc": "2.0", "result": {"value": None}, "id": 7}


def test_named_params_are_preserved_for_integration_adapter():
    transport = JsonRpcTransport(lambda _method, params: params)

    response = _decode(
        transport.handle_bytes(
            b'{"jsonrpc":"2.0","method":"named","params":{"left":1},"id":"n"}'
        )
    )

    assert response["result"] == {"left": 1}


def test_batch_preserves_order_and_omits_notification_responses():
    calls = []
    transport = JsonRpcTransport(
        lambda method, params: calls.append((method, params)) or params[0]
    )
    document = [
        {"jsonrpc": "2.0", "method": "notify", "params": [1]},
        {"jsonrpc": "2.0", "method": "call", "params": [2], "id": "two"},
        17,
        {"jsonrpc": "2.0", "method": "notify", "params": [3]},
    ]

    response = _decode(transport.handle_bytes(json.dumps(document).encode()))

    assert calls == [("notify", (1,)), ("call", (2,)), ("notify", (3,))]
    assert response == [
        {"jsonrpc": "2.0", "result": 2, "id": "two"},
        {
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Invalid Request"},
            "id": None,
        },
    ]


def test_notification_only_batch_has_no_response_even_when_dispatch_fails():
    def dispatch(method, _params):
        if method == "fail":
            raise RuntimeError("secret details")
        return True

    transport = JsonRpcTransport(dispatch)
    payload = json.dumps(
        [
            {"jsonrpc": "2.0", "method": "ok"},
            {"jsonrpc": "2.0", "method": "fail"},
        ]
    ).encode()

    assert transport.handle_bytes(payload) is None


@pytest.mark.parametrize("payload", [b"{", b'"scalar"', b"[]", b"NaN"])
def test_malformed_and_invalid_documents_return_standard_errors(payload):
    transport = JsonRpcTransport(lambda *_args: None)

    response = _decode(transport.handle_bytes(payload))

    expected_code = -32700 if payload in {b"{", b"NaN"} else -32600
    assert response["jsonrpc"] == "2.0"
    assert response["error"]["code"] == expected_code
    assert response["id"] is None


@pytest.mark.parametrize(
    "request_document",
    [
        {"method": "missing-version", "id": 1},
        {"jsonrpc": "1.0", "method": "old", "id": 2},
        {"jsonrpc": "2.0", "method": 3, "id": 3},
        {"jsonrpc": "2.0", "method": "bad-params", "params": 4, "id": 4},
        {"jsonrpc": "2.0", "method": "bad-id", "id": True},
    ],
)
def test_invalid_request_members_are_not_dispatched(request_document):
    transport = JsonRpcTransport(
        lambda *_args: (_ for _ in ()).throw(AssertionError("dispatched"))
    )

    response = _decode(transport.handle_bytes(json.dumps(request_document).encode()))

    assert response["error"]["code"] == -32600


def test_null_and_signed_64_bit_integers_round_trip_without_coercion():
    transport = JsonRpcTransport(lambda _method, params: params[0])
    value = {
        "none": None,
        "maximum": 9_223_372_036_854_775_807,
        "minimum": -9_223_372_036_854_775_808,
    }
    request = {"jsonrpc": "2.0", "method": "echo", "params": [value], "id": 1}

    response = _decode(transport.handle_bytes(json.dumps(request).encode()))

    assert response["result"] == value
    assert isinstance(response["result"]["maximum"], int)


def test_structured_error_exception_is_returned_without_losing_data():
    def dispatch(_method, _params):
        raise JsonRpcError(
            -32041,
            "Revision conflict",
            {"expected_revision": 7, "current_revision": 9},
        )

    response = _decode(
        JsonRpcTransport(dispatch).handle_bytes(
            b'{"jsonrpc":"2.0","method":"mutate","id":4}'
        )
    )

    assert response == {
        "jsonrpc": "2.0",
        "error": {
            "code": -32041,
            "message": "Revision conflict",
            "data": {"expected_revision": 7, "current_revision": 9},
        },
        "id": 4,
    }


def test_result_to_error_callback_converts_only_selected_results():
    def result_to_error(result):
        if result.get("success") is False:
            return {"code": -32042, "message": "Cancelled", "data": result}
        return None

    transport = JsonRpcTransport(
        lambda method, _params: {"success": method == "ok", "method": method},
        result_to_error=result_to_error,
    )

    failed = _decode(
        transport.handle_bytes(b'{"jsonrpc":"2.0","method":"cancel","id":1}')
    )
    succeeded = _decode(
        transport.handle_bytes(b'{"jsonrpc":"2.0","method":"ok","id":2}')
    )

    assert failed["error"]["code"] == -32042
    assert failed["error"]["data"]["success"] is False
    assert succeeded["result"] == {"success": True, "method": "ok"}


def test_production_result_error_mapper_plugs_into_transport():
    transport = JsonRpcTransport(
        lambda _method, _params: {
            "success": False,
            "error_code": "STALE_REVISION",
            "message": "Revision changed",
            "expected_revision": 7,
            "current_revision": 9,
        },
        result_to_error=json_rpc_error_from_result,
    )

    response = _decode(
        transport.handle_bytes(b'{"jsonrpc":"2.0","method":"mutate","id":3}')
    )

    assert response == {
        "jsonrpc": "2.0",
        "id": 3,
        "error": {
            "code": -32002,
            "message": "Revision changed",
            "data": {
                "expected_revision": 7,
                "current_revision": 9,
                "error_code": "STALE_REVISION",
            },
        },
    }


def test_unexpected_or_unencodable_results_become_opaque_internal_errors():
    for result in (object(), float("nan")):
        response = _decode(
            JsonRpcTransport(lambda *_args, value=result: value).handle_bytes(
                b'{"jsonrpc":"2.0","method":"bad","id":5}'
            )
        )
        assert response == {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": "Internal error"},
            "id": 5,
        }


def test_dispatch_failures_do_not_leak_exception_messages_to_logs(caplog):
    def dispatch(*_args):
        raise RuntimeError("TOP_SECRET_TOKEN")

    caplog.set_level(logging.DEBUG, logger="FreeCADMCP.rpc_server")
    transport = JsonRpcTransport(dispatch)

    response = _decode(
        transport.handle_bytes(b'{"jsonrpc":"2.0","method":"bad","id":5}')
    )
    notification = transport.handle_bytes(
        b'{"jsonrpc":"2.0","method":"bad-notification"}'
    )

    assert response["error"] == {"code": -32603, "message": "Internal error"}
    assert notification is None
    assert "TOP_SECRET_TOKEN" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_shutdown_rejects_requests_and_silences_notifications():
    calls = []
    transport = JsonRpcTransport(lambda method, _params: calls.append(method))
    transport.begin_shutdown()

    response = _decode(
        transport.handle_bytes(b'{"jsonrpc":"2.0","method":"late","id":8}')
    )
    notification = transport.handle_bytes(
        b'{"jsonrpc":"2.0","method":"late-notification"}'
    )

    assert response["error"] == {"code": -32004, "message": "Server stopping"}
    assert notification is None
    assert calls == []
