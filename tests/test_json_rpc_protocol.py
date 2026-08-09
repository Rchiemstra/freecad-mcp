"""JSON-RPC framing contracts for the byte-identical protocol vendors."""

from __future__ import annotations

import json

import pytest

from addon.FreeCADMCP._shared.protocol.handshake_request import sign_handshake_request
from addon.FreeCADMCP._shared.protocol.json_rpc import (
    JSON_RPC_INVALID_REQUEST,
    JSON_RPC_PARSE_ERROR,
    JsonRpcFramingError,
    JsonRpcInvalidRequest,
    JsonRpcRequest,
    decode_json_rpc_payload,
    encode_json_rpc_responses,
    json_rpc_error,
    json_rpc_success,
)
from addon.FreeCADMCP._shared.protocol.request_envelope import RequestEnvelope
from addon.FreeCADMCP._shared.protocol.request_replay_cache import RequestReplayCache

pytestmark = pytest.mark.unit


def test_single_request_preserves_null_and_64_bit_values() -> None:
    request = {
        "jsonrpc": "2.0",
        "id": 9_223_372_036_854_775_000,
        "method": "save_document",
        "params": {"doc_name": "D", "expected_revision": None},
    }

    decoded = decode_json_rpc_payload(json.dumps(request).encode())

    assert decoded.batch is False
    assert decoded.requests == (
        JsonRpcRequest(
            method="save_document",
            params={"doc_name": "D", "expected_revision": None},
            request_id=9_223_372_036_854_775_000,
            notification=False,
        ),
    )


def test_batch_distinguishes_notifications_and_invalid_members() -> None:
    decoded = decode_json_rpc_payload(
        json.dumps(
            [
                {"jsonrpc": "2.0", "method": "cancel_request", "params": ["r"]},
                {"jsonrpc": "2.0", "id": "two", "method": "ping"},
                {"jsonrpc": "1.0", "id": "bad", "method": "ping"},
                3,
            ]
        )
    )

    assert decoded.batch is True
    assert decoded.requests[0] == JsonRpcRequest(
        method="cancel_request", params=["r"], request_id=None, notification=True
    )
    assert decoded.requests[1] == JsonRpcRequest(
        method="ping", params=[], request_id="two", notification=False
    )
    assert decoded.requests[2:] == (
        JsonRpcInvalidRequest(request_id="bad"),
        JsonRpcInvalidRequest(),
    )


@pytest.mark.parametrize(
    "payload",
    [b"", b"{", b'"\\ud800"', b'{"value":NaN}', b"\xff"],
)
def test_malformed_json_is_a_parse_error(payload: bytes) -> None:
    with pytest.raises(JsonRpcFramingError) as exc_info:
        decode_json_rpc_payload(payload)

    assert exc_info.value.code == JSON_RPC_PARSE_ERROR
    assert exc_info.value.message == "Parse error"


@pytest.mark.parametrize("depth", [129, 1_200])
def test_excessive_json_depth_is_an_opaque_parse_error(depth: int) -> None:
    payload = (b"[" * depth) + b"0" + (b"]" * depth)

    with pytest.raises(JsonRpcFramingError) as exc_info:
        decode_json_rpc_payload(payload)

    assert exc_info.value.code == JSON_RPC_PARSE_ERROR
    assert exc_info.value.message == "Parse error"


def test_excessive_json_item_count_is_an_opaque_parse_error() -> None:
    payload = b"[" + (b"0," * 100_000) + b"0]"

    with pytest.raises(JsonRpcFramingError) as exc_info:
        decode_json_rpc_payload(payload)

    assert exc_info.value.code == JSON_RPC_PARSE_ERROR


def test_excessive_batch_count_is_bounded_as_an_invalid_request() -> None:
    member = {"jsonrpc": "2.0", "method": "ping"}

    with pytest.raises(JsonRpcFramingError) as exc_info:
        decode_json_rpc_payload(json.dumps([member] * 1_025))

    assert exc_info.value.code == JSON_RPC_INVALID_REQUEST
    assert exc_info.value.message == "Invalid Request"


@pytest.mark.parametrize("payload", [[], True, 4, "request"])
def test_non_request_top_levels_are_invalid_requests(payload: object) -> None:
    decoded = decode_json_rpc_payload(json.dumps(payload))

    assert decoded.requests == (JsonRpcInvalidRequest(),)
    assert decoded.batch is False


def test_response_encoding_omits_notification_bodies() -> None:
    assert encode_json_rpc_responses([], batch=False) == b""
    success = json_rpc_success("request", {"revision": 9_223_372_036_854_775_000})
    error = json_rpc_error(
        None,
        JSON_RPC_INVALID_REQUEST,
        "Invalid Request",
        {"semantic_code": "MALFORMED_REQUEST"},
    )

    assert json.loads(encode_json_rpc_responses([success], batch=False)) == success
    assert json.loads(encode_json_rpc_responses([success, error], batch=True)) == [
        success,
        error,
    ]


def test_json_framing_preserves_handshake_proof_bytes() -> None:
    secret = b"s" * 32
    signed = sign_handshake_request(
        {
            "kind": "freecad-mcp-handshake-v2",
            "protocol_version": 2,
            "nonce": "n" * 32,
            "nested": {"nullable": None, "revision": 9_223_372_036_854_775_000},
        },
        secret,
    )
    request = {
        "jsonrpc": "2.0",
        "id": "handshake",
        "method": "handshake_v2",
        "params": [signed],
    }

    decoded = decode_json_rpc_payload(json.dumps(request))
    transported = decoded.requests[0]

    assert isinstance(transported, JsonRpcRequest)
    assert transported.params == [signed]
    assert sign_handshake_request(transported.params[0], secret)["proof"] == signed["proof"]


def test_json_framing_preserves_authenticated_replay_identity() -> None:
    runtime_id = "11111111-1111-4111-8111-111111111111"
    envelope_payload = {
        "protocol_version": 2,
        "request_id": "22222222-2222-4222-8222-222222222222",
        "session_token": "s" * 32,
        "method": "ping",
        "params": {"nullable": None},
        "lease_credentials": [],
    }
    request = {
        "jsonrpc": "2.0",
        "id": envelope_payload["request_id"],
        "method": "invoke_v2",
        "params": [envelope_payload],
    }
    decoded = decode_json_rpc_payload(json.dumps(request))
    transported = decoded.requests[0]

    assert isinstance(transported, JsonRpcRequest)
    first = RequestEnvelope.from_dict(transported.params[0])
    replay = RequestReplayCache()
    assert replay.claim(runtime_id, first).status == "new"
    replay.complete(
        runtime_id,
        first,
        {"ok": True, "result": {"revision": 9_223_372_036_854_775_000}},
    )

    repeated = RequestEnvelope.from_dict(transported.params[0])
    cached = replay.claim(runtime_id, repeated)
    assert cached.status == "completed"
    response = json_rpc_success(request["id"], cached.response)
    round_trip = json.loads(encode_json_rpc_responses([response], batch=False))
    assert round_trip["result"] == {
        "ok": True,
        "result": {"revision": 9_223_372_036_854_775_000},
    }
