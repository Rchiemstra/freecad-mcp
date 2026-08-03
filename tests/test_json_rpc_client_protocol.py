"""Shared JSON-RPC client framing and negotiation contracts."""

from __future__ import annotations

import json

import pytest

from freecad_mcp._shared.protocol.json_rpc_client import (
    JSON_RPC_PROTOCOL_VALUE,
    JsonRpcProtocolMismatchError,
    JsonRpcRemoteError,
    decode_json_rpc_response,
    encode_json_rpc_request,
)

pytestmark = pytest.mark.unit


def test_request_and_notification_encoding_preserve_wire_values():
    request = json.loads(
        encode_json_rpc_request(
            "save_document",
            ("Doc", {"expected_revision": None}),
            request_id=9_223_372_036_854_775_000,
        )
    )
    notification = json.loads(
        encode_json_rpc_request("cancel_request", ("request",), notification=True)
    )

    assert request == {
        "jsonrpc": "2.0",
        "method": "save_document",
        "params": ["Doc", {"expected_revision": None}],
        "id": 9_223_372_036_854_775_000,
    }
    assert notification == {
        "jsonrpc": "2.0",
        "method": "cancel_request",
        "params": ["request"],
    }


def test_response_result_is_validated_and_returned():
    result = decode_json_rpc_response(
        b'{"jsonrpc":"2.0","id":"r","result":{"value":null}}',
        expected_id="r",
    )

    assert result == {"value": None}


def test_remote_error_is_native_structured_and_independently_copied():
    with pytest.raises(JsonRpcRemoteError) as caught:
        decode_json_rpc_response(
            b'{"jsonrpc":"2.0","id":7,"error":{"code":-32002,'
            b'"message":"Revision changed","data":{"error_code":"STALE_REVISION",'
            b'"current_revision":9}}}',
            expected_id=7,
        )

    assert caught.value.code == -32002
    assert caught.value.semantic_code == "STALE_REVISION"
    assert caught.value.message == "Revision changed"
    assert caught.value.data == {
        "error_code": "STALE_REVISION",
        "current_revision": 9,
    }


@pytest.mark.parametrize(
    ("payload", "expected_id", "message"),
    [
        (b"not-json", 1, "valid JSON-RPC 2.0"),
        (b'{"jsonrpc":"1.0","id":1,"result":true}', 1, "version mismatch"),
        (b'{"jsonrpc":"2.0","id":2,"result":true}', 1, "did not match"),
        (b'{"jsonrpc":"2.0","id":1}', 1, "exactly one"),
        (
            b'{"jsonrpc":"2.0","id":1,"result":true,"error":{}}',
            1,
            "exactly one",
        ),
        (b'{"jsonrpc":"2.0","id":1,"error":{"code":true,"message":"x"}}', 1, "invalid error"),
    ],
)
def test_protocol_mismatch_responses_are_clear(payload, expected_id, message):
    with pytest.raises(JsonRpcProtocolMismatchError, match=message) as caught:
        decode_json_rpc_response(payload, expected_id=expected_id)

    assert caught.value.expected == JSON_RPC_PROTOCOL_VALUE


def test_request_encoder_rejects_non_finite_and_oversized_values():
    with pytest.raises(ValueError, match="not encodable"):
        encode_json_rpc_request("bad", (float("nan"),), request_id=1)
    with pytest.raises(ValueError, match="transport limit"):
        encode_json_rpc_request("large", ("x" * (4 * 1024 * 1024),), request_id=1)
