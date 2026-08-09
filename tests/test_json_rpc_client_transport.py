"""Focused JSON-RPC client HTTP transport tests."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from freecad_mcp._shared.protocol.json_rpc_client import (
    JSON_RPC_HTTP_PATH,
    JSON_RPC_PROTOCOL_HEADER,
    JSON_RPC_PROTOCOL_VALUE,
    JsonRpcProtocolMismatchError,
    JsonRpcRemoteError,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.freecad_client_ops.connection_methods.connection_control_ops import (
    notify_cancel_request,
)
from freecad_mcp.freecad_client_ops.json_rpc_http_transport import (
    JsonRpcHttpTransport,
)
from freecad_mcp.freecad_client_ops.proxy_lane import ProxyLane
from freecad_mcp.freecad_client_ops.timeout_transport import TimeoutTransport

pytestmark = pytest.mark.unit


def test_legacy_xmlrpc_import_is_declarative_and_has_no_live_call_path():
    import freecad_mcp.freecad_client as client_module

    assert client_module.xmlrpc.client.ServerProxy is not None
    root = Path(__file__).resolve().parents[1]
    sources = [root / "src/freecad_mcp/freecad_client.py"]
    sources.extend((root / "src/freecad_mcp/freecad_client_ops").rglob("*.py"))
    assert all(
        "ServerProxy(" not in path.read_text(encoding="utf-8") for path in sources
    )


class _StubTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.extra_headers = []
        self.closed = False

    def request(self, path, payload, headers):
        self.requests.append((path, json.loads(payload), dict(headers)))
        return self.responses.pop(0)

    def close(self):
        self.closed = True


def _response(document, *, protocol=JSON_RPC_PROTOCOL_VALUE, status=200):
    headers = (
        {}
        if protocol is None
        else {JSON_RPC_PROTOCOL_HEADER.lower(): (protocol,)}
    )
    body = document if isinstance(document, bytes) else json.dumps(document).encode()
    return status, headers, body


def _lane_with_responses(*responses, headers=()):
    lane = ProxyLane("http://127.0.0.1:1", 5, lambda *_args: tuple(headers))
    lane.transport.close()
    transport = _StubTransport(responses)
    lane.transport = transport
    return lane, transport


def test_proxy_lane_uses_jsonrpc_path_headers_ids_and_result():
    wide = 9_223_372_036_854_775_807
    lane, transport = _lane_with_responses(
        _response({"jsonrpc": "2.0", "id": 1, "result": {"wide": wide}}),
        headers=(("X-MCP-Instance-Id", "runtime-1"),),
    )

    result = lane.call("document.read", None)

    path, document, headers = transport.requests[0]
    assert path == JSON_RPC_HTTP_PATH
    assert document == {
        "jsonrpc": "2.0",
        "method": "document.read",
        "params": [None],
        "id": 1,
    }
    assert headers["X-MCP-Instance-Id"] == "runtime-1"
    assert headers[JSON_RPC_PROTOCOL_HEADER] == JSON_RPC_PROTOCOL_VALUE
    assert result == {"wide": wide}
    assert transport.extra_headers == []


def test_request_ids_are_validated_and_advance_per_lane():
    lane, transport = _lane_with_responses(
        _response({"jsonrpc": "2.0", "id": 1, "result": "first"}),
        _response({"jsonrpc": "2.0", "id": 2, "result": "second"}),
    )

    assert lane.call("first") == "first"
    assert lane.call("second") == "second"
    assert [item[1]["id"] for item in transport.requests] == [1, 2]


def test_structured_remote_error_is_a_native_exception_with_data():
    lane, _transport = _lane_with_responses(
        _response(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32002,
                    "message": "Revision changed",
                    "data": {
                        "error_code": "STALE_REVISION",
                        "expected_revision": 7,
                        "current_revision": 9,
                    },
                },
            }
        )
    )

    with pytest.raises(JsonRpcRemoteError) as raised:
        lane.call("mutate")

    assert raised.value.code == -32002
    assert raised.value.semantic_code == "STALE_REVISION"
    assert raised.value.request_id == 1
    assert raised.value.data == {
        "error_code": "STALE_REVISION",
        "expected_revision": 7,
        "current_revision": 9,
    }


def test_remote_error_unwraps_nested_invoke_v2_failure_message():
    lane, _transport = _lane_with_responses(
        _response(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": "RPC failed",
                    "data": {
                        "request_id": "request-1",
                        "addon_runtime_id": "runtime-1",
                        "result": {
                            "success": False,
                            "error_code": "gui_timeout_not_supported",
                            "error": "timeout_seconds is a hard worker timeout",
                        },
                    },
                },
            }
        )
    )

    with pytest.raises(JsonRpcRemoteError) as raised:
        lane.call("get_gui_state")

    assert raised.value.message == "timeout_seconds is a hard worker timeout"
    assert raised.value.semantic_code == "gui_timeout_not_supported"
    assert raised.value.data["error_code"] == "gui_timeout_not_supported"
    assert (
        str(raised.value)
        == "FreeCAD RPC error -32000: timeout_seconds is a hard worker timeout"
    )
    assert raised.value.data["result"]["error"] == (
        "timeout_seconds is a hard worker timeout"
    )


class _HeaderErrorEchoHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        session = self.headers["X-MCP-Session-Token"]
        credentials = json.loads(self.headers["X-MCP-Lease-Credentials"])
        lease_tokens = [item["token"] for item in credentials]
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {
                    "code": -32000,
                    "message": f"peer echoed {session} and {lease_tokens[0]}",
                    "data": {
                        "detail": [session, lease_tokens[0], lease_tokens[1]],
                    },
                },
            }
        ).encode()
        self.send_response(200)
        self.send_header(JSON_RPC_PROTOCOL_HEADER, JSON_RPC_PROTOCOL_VALUE)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


def test_direct_remote_error_scrubs_session_and_multi_credential_header_secrets():
    secrets = ("direct-session-secret", "lease-secret-a", "lease-secret-b")
    credentials = json.dumps(
        [{"token": secrets[1]}, {"token": secrets[2]}], separators=(",", ":")
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HeaderErrorEchoHandler)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    lane = ProxyLane(
        f"http://127.0.0.1:{server.server_address[1]}",
        2,
        lambda *_args: (
            ("X-MCP-Session-Token", secrets[0]),
            ("X-MCP-Lease-Credentials", credentials),
        ),
    )
    try:
        with pytest.raises(JsonRpcRemoteError) as raised:
            lane.call("direct_read")
    finally:
        lane.close()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)

    rendered = f"{raised.value} {raised.value.data}"
    assert all(secret not in rendered for secret in secrets)
    assert "[REDACTED]" in raised.value.message
    assert raised.value.data == {
        "detail": ["[REDACTED]", "[REDACTED]", "[REDACTED]"]
    }


def test_remote_error_identity_is_preserved_when_headers_are_not_echoed(monkeypatch):
    import freecad_mcp.freecad_client_ops.proxy_lane as proxy_lane_module

    original = JsonRpcRemoteError(-32000, "safe remote error", data={"safe": True})

    def raise_original(*_args, **_kwargs):
        raise original

    monkeypatch.setattr(proxy_lane_module, "decode_json_rpc_response", raise_original)
    lane, _transport = _lane_with_responses(
        _response({"jsonrpc": "2.0", "id": 1, "result": True}),
        headers=(("X-MCP-Session-Token", "secret-not-echoed"),),
    )

    with pytest.raises(JsonRpcRemoteError) as raised:
        lane.call("direct_read")

    assert raised.value is original


@pytest.mark.parametrize(
    "response",
    [
        _response({"jsonrpc": "2.0", "id": 1, "result": True}, protocol=None),
        _response(
            {"jsonrpc": "2.0", "id": 1, "result": True},
            protocol="xmlrpc-deprecated",
        ),
        _response({"jsonrpc": "1.0", "id": 1, "result": True}),
        _response({"jsonrpc": "2.0", "id": 99, "result": True}),
        _response(
            {"jsonrpc": "2.0", "id": 1, "result": True, "error": {}},
        ),
        _response(b"<methodResponse></methodResponse>"),
        _response(b"", protocol=None, status=426),
    ],
)
def test_legacy_or_invalid_responses_raise_clear_protocol_mismatch(response):
    lane, _transport = _lane_with_responses(response)

    with pytest.raises(JsonRpcProtocolMismatchError, match="FreeCAD RPC"):
        lane.call("ping")


def test_notifications_omit_id_and_require_empty_204_response():
    lane, transport = _lane_with_responses(
        _response(b"", status=204),
    )

    assert lane.notify("cancel_request", {"target_request_id": "request-1"}) is None

    _, document, _ = transport.requests[0]
    assert document == {
        "jsonrpc": "2.0",
        "method": "cancel_request",
        "params": [{"target_request_id": "request-1"}],
    }


def test_unexpected_notification_response_is_protocol_mismatch():
    lane, _transport = _lane_with_responses(
        _response({"jsonrpc": "2.0", "id": None, "result": True}),
    )

    with pytest.raises(JsonRpcProtocolMismatchError, match="notification"):
        lane.notify("cancel_request", {})


class _EchoHandler(BaseHTTPRequestHandler):
    calls: ClassVar[list] = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        type(self).calls.append((self.path, dict(self.headers), request))
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": request["id"], "result": request["params"]}
        ).encode()
        self.send_response(200)
        self.send_header(JSON_RPC_PROTOCOL_HEADER, JSON_RPC_PROTOCOL_VALUE)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


def test_live_stdlib_http_round_trip_preserves_identity_headers():
    _EchoHandler.calls = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _EchoHandler)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    lane = ProxyLane(
        f"http://127.0.0.1:{server.server_address[1]}",
        2,
        lambda *_args: (("X-MCP-Instance-Id", "runtime-live"),),
    )
    try:
        assert lane.call("echo", None, 9_223_372_036_854_775_807) == [
            None,
            9_223_372_036_854_775_807,
        ]
    finally:
        lane.close()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)

    path, headers, request = _EchoHandler.calls[0]
    assert path == JSON_RPC_HTTP_PATH
    assert headers["X-MCP-Instance-Id"] == "runtime-live"
    assert headers[JSON_RPC_PROTOCOL_HEADER] == JSON_RPC_PROTOCOL_VALUE
    assert request["method"] == "echo"


class _NotificationHandler(BaseHTTPRequestHandler):
    calls: ClassVar[list] = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        type(self).calls.append((self.path, dict(self.headers), request))
        self.send_response(204)
        self.send_header(JSON_RPC_PROTOCOL_HEADER, JSON_RPC_PROTOCOL_VALUE)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, _format, *_args):
        return


def test_task_cancellation_uses_authenticated_notification_without_response_id():
    target = "4d70e4e7-9bd8-410b-bd73-f5e49eb60cb5"
    _NotificationHandler.calls = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _NotificationHandler)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    connection = FreeCADConnection(
        host="127.0.0.1",
        port=server.server_address[1],
        mcp_instance_id="runtime-notification",
    )

    class _Context:
        @staticmethod
        def to_envelope(method, params):
            return {
                "protocol_version": 2,
                "session_token": "authenticated-session",
                "request_id": "advisory-request",
                "method": method,
                "params": params,
            }

    connection._build_v2_context = lambda **_kwargs: _Context()
    try:
        assert notify_cancel_request(connection, target) is True
    finally:
        connection.disconnect()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)

    path, headers, request = _NotificationHandler.calls[0]
    assert path == JSON_RPC_HTTP_PATH
    assert "id" not in request
    assert request["method"] == "invoke_v2_control"
    assert request["params"][0]["session_token"] == "authenticated-session"
    assert request["params"][0]["params"] == {"target_request_id": target}
    assert headers["X-MCP-Instance-Id"] == "runtime-notification"
    assert headers[JSON_RPC_PROTOCOL_HEADER] == JSON_RPC_PROTOCOL_VALUE


def _start_adversarial_server(mode, *, timeout=0.15):
    started = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            request = json.loads(self.rfile.read(length))
            payload = json.dumps(
                {"jsonrpc": "2.0", "id": request["id"], "result": True}
            ).encode()
            self.send_response(200)
            if mode == "duplicate_protocol":
                self.send_header(JSON_RPC_PROTOCOL_HEADER, "incompatible")
            self.send_header(JSON_RPC_PROTOCOL_HEADER, JSON_RPC_PROTOCOL_VALUE)
            declared = len(payload) + 10 if mode == "short_body" else len(payload)
            declared_text = str(declared)
            if mode == "plus_length":
                declared_text = f"+{declared}"
            elif mode == "underscore_length":
                digits = str(declared)
                declared_text = f"{digits[:-1]}_{digits[-1]}"
            self.send_header("Content-Length", declared_text)
            if mode == "duplicate_length":
                self.send_header("Content-Length", declared_text)
            self.end_headers()
            started.set()
            try:
                if mode == "drip":
                    for item in payload:
                        self.wfile.write(bytes((item,)))
                        self.wfile.flush()
                        time.sleep(0.04)
                else:
                    self.wfile.write(payload)
            except OSError:
                return

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    lane = ProxyLane(
        f"http://127.0.0.1:{server.server_address[1]}",
        timeout,
        lambda *_args: (),
    )
    return server, loop, lane, started


def _stop_adversarial_server(server, loop, lane):
    lane.close()
    server.shutdown()
    server.server_close()
    loop.join(timeout=2)


@pytest.mark.parametrize(
    "mode",
    ["short_body", "duplicate_length", "plus_length", "underscore_length"],
)
def test_ambiguous_or_incomplete_http_framing_is_rejected(mode):
    server, loop, lane, _started = _start_adversarial_server(mode, timeout=2)
    try:
        with pytest.raises(JsonRpcProtocolMismatchError, match="bounded HTTP"):
            lane.call("ping")
    finally:
        _stop_adversarial_server(server, loop, lane)


def test_duplicate_protocol_headers_are_rejected_even_if_last_value_matches():
    server, loop, lane, _started = _start_adversarial_server(
        "duplicate_protocol", timeout=2
    )
    try:
        with pytest.raises(JsonRpcProtocolMismatchError, match="header mismatch"):
            lane.call("ping")
    finally:
        _stop_adversarial_server(server, loop, lane)


def test_response_deadline_rejects_a_peer_that_drips_within_socket_timeout():
    server, loop, lane, _started = _start_adversarial_server("drip", timeout=0.15)
    started_at = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="deadline"):
            lane.call("ping")
        assert time.monotonic() - started_at < 0.75
    finally:
        _stop_adversarial_server(server, loop, lane)


def test_close_aborts_active_response_without_waiting_for_lane_call_lock():
    server, loop, lane, started = _start_adversarial_server("drip", timeout=5)
    outcomes = []

    def call():
        try:
            lane.call("ping")
        except BaseException as exc:
            outcomes.append(exc)

    caller = threading.Thread(target=call)
    caller.start()
    try:
        assert started.wait(timeout=2)
        started_at = time.monotonic()
        lane.close()
        assert time.monotonic() - started_at < 0.5
        caller.join(timeout=1)
        assert not caller.is_alive()
        assert outcomes
    finally:
        _stop_adversarial_server(server, loop, lane)


def test_transport_close_prevents_reuse_and_compatibility_import_is_declarative():
    assert TimeoutTransport is JsonRpcHttpTransport
    transport = TimeoutTransport("http://127.0.0.1:1", timeout=1)
    transport.close()

    with pytest.raises(RuntimeError, match="closed"):
        transport.request(JSON_RPC_HTTP_PATH, b"{}", ())
