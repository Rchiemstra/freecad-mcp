"""Phase 4 dual-listener integration contracts."""

from __future__ import annotations

import http.client
import json
import socket
import threading
import urllib.error
import urllib.request

import pytest

from addon.FreeCADMCP.rpc_server import xmlrpc_identity_handler
from addon.FreeCADMCP.rpc_server.filtered_xmlrpc_server import FilteredXMLRPCServer

pytestmark = pytest.mark.unit


class _IdentityContext:
    def __init__(self):
        self.local = threading.local()
        self.captured = []
        self.cleared = 0
        self.lock = threading.Lock()

    def set_request_identity(self, **identity):
        self.local.identity = identity
        with self.lock:
            self.captured.append(identity)

    def get_request_identity(self):
        return getattr(self.local, "identity", {})

    def clear_request_identity(self):
        if hasattr(self.local, "identity"):
            del self.local.identity
        with self.lock:
            self.cleared += 1


class _Methods:
    def __init__(self, identity):
        self.identity = identity
        self.named_calls = []
        self.ping_calls = 0

    def add(self, left, right=2):
        self.named_calls.append((left, right))
        return left + right

    def identity_headers(self):
        return self.identity.get_request_identity()

    def legacy_failure(self):
        return {
            "success": False,
            "error_code": "STALE_REVISION",
            "message": "Revision changed",
            "expected_revision": 7,
            "current_revision": 9,
        }

    def wide_integer(self):
        return 9_223_372_036_854_775_000

    def ping(self):
        self.ping_calls += 1
        return True


class _LaneMethods:
    def __init__(self):
        self.release = threading.Event()
        self.three_started = threading.Event()
        self.lock = threading.Lock()
        self.active = 0

    def slow(self, value):
        with self.lock:
            self.active += 1
            if self.active == 3:
                self.three_started.set()
        try:
            assert self.release.wait(timeout=3)
            return value
        finally:
            with self.lock:
                self.active -= 1

    def ping(self):
        return True


def _json_request(port, document, *, headers=None):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/jsonrpc",
        data=json.dumps(document, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        payload = response.read()
        return response.status, json.loads(payload) if payload else None


def test_jsonrpc_dispatch_and_identity_survive_xmlrpc_retirement(monkeypatch):
    identity = _IdentityContext()
    methods = _Methods(identity)
    monkeypatch.setattr(
        xmlrpc_identity_handler, "_identity_bindings", lambda: identity
    )
    server = FilteredXMLRPCServer(
        ("127.0.0.1", 0),
        allowed_ips_str="127.0.0.1",
        allow_none=True,
        logRequests=False,
    )
    server.register_instance(methods)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    port = server.server_address[1]
    try:
        status, named = _json_request(
            port,
            {
                "jsonrpc": "2.0",
                "method": "add",
                "params": {"right": 5, "left": 6},
                "id": 1,
            },
        )
        _, captured = _json_request(
            port,
            {"jsonrpc": "2.0", "method": "identity_headers", "id": 2},
            headers={"X-MCP-Instance-Id": "runtime-1", "X-MCP-Pid": "123"},
        )
        _, failure = _json_request(
            port, {"jsonrpc": "2.0", "method": "legacy_failure", "id": 3}
        )
        _, wide = _json_request(
            port, {"jsonrpc": "2.0", "method": "wide_integer", "id": 4}
        )
    finally:
        server.begin_shutdown()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)

    assert status == 200
    assert named == {"jsonrpc": "2.0", "id": 1, "result": 11}
    assert methods.named_calls == [(6, 5)]
    assert captured["result"]["instance_id"] == "runtime-1"
    assert captured["result"]["pid"] == 123
    assert failure["error"] == {
        "code": -32002,
        "message": "Revision changed",
        "data": {
            "expected_revision": 7,
            "current_revision": 9,
            "error_code": "STALE_REVISION",
        },
    }
    assert wide["result"] == 9_223_372_036_854_775_000
    assert identity.cleared == 4


def test_jsonrpc_method_and_parameter_errors_do_not_dispatch():
    identity = _IdentityContext()
    methods = _Methods(identity)
    server = FilteredXMLRPCServer(
        ("127.0.0.1", 0),
        allowed_ips_str="127.0.0.1",
        allow_none=True,
        logRequests=False,
    )
    server.register_instance(methods)

    missing = json.loads(
        server._json_rpc_transport.handle_bytes(
            b'{"jsonrpc":"2.0","method":"missing","id":1}'
        )
    )
    invalid = json.loads(
        server._json_rpc_transport.handle_bytes(
            b'{"jsonrpc":"2.0","method":"add","params":[1,2,3],"id":2}'
        )
    )
    try:
        assert missing["error"] == {"code": -32601, "message": "Method not found"}
        assert invalid["error"] == {
            "code": -32602,
            "message": "Invalid params",
        }
        assert methods.named_calls == []
    finally:
        server.server_close()


def test_shared_listener_bounds_body_reads_and_recovers_worker():
    identity = _IdentityContext()
    server = FilteredXMLRPCServer(
        ("127.0.0.1", 0),
        allowed_ips_str="127.0.0.1",
        allow_none=True,
        logRequests=False,
    )
    server.register_instance(_Methods(identity))
    server.json_rpc_read_timeout_seconds = 0.1
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    stalled = socket.create_connection(server.server_address, timeout=2)
    stalled.settimeout(2)
    try:
        stalled.sendall(
            b"POST /jsonrpc HTTP/1.1\r\nHost: localhost\r\n"
            b"Content-Length: 100\r\n\r\n{}"
        )
        timeout_response = stalled.recv(4096)
        status, ready = _json_request(
            server.server_address[1],
            {"jsonrpc": "2.0", "method": "ping", "id": 1},
        )
        notification_status, notification = _json_request(
            server.server_address[1],
            {"jsonrpc": "2.0", "method": "ping"},
        )
        server.json_rpc_max_body_bytes = 4
        oversized = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/jsonrpc",
            data=b"12345",
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(oversized, timeout=2)
    finally:
        stalled.close()
        server.begin_shutdown()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)

    assert b" 408 " in timeout_response
    assert status == 200
    assert ready["result"] is True
    assert notification_status == 204
    assert notification is None
    assert caught.value.code == 413


def test_shared_listener_rejects_eof_short_body_without_dispatch():
    identity = _IdentityContext()
    methods = _Methods(identity)
    server = FilteredXMLRPCServer(
        ("127.0.0.1", 0),
        allowed_ips_str="127.0.0.1",
        allow_none=True,
        logRequests=False,
    )
    server.register_instance(methods)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    connection = socket.create_connection(server.server_address, timeout=2)
    connection.settimeout(2)
    body = b'{"jsonrpc":"2.0","method":"ping","id":1}'
    try:
        connection.sendall(
            b"POST /jsonrpc HTTP/1.1\r\nHost: localhost\r\nContent-Length: "
            + str(len(body) + 100).encode()
            + b"\r\n\r\n"
            + body
        )
        connection.shutdown(socket.SHUT_WR)
        response = connection.recv(4096)
    finally:
        connection.close()
        server.begin_shutdown()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)

    assert b" 400 " in response
    assert methods.ping_calls == 0


def test_shared_listener_bounds_incomplete_headers_before_body_parsing():
    identity = _IdentityContext()
    methods = _Methods(identity)
    server = FilteredXMLRPCServer(
        ("127.0.0.1", 0),
        allowed_ips_str="127.0.0.1",
        allow_none=True,
        logRequests=False,
    )
    server.register_instance(methods)
    server.json_rpc_read_timeout_seconds = 0.1
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    stalled = [
        socket.create_connection(server.server_address, timeout=2) for _ in range(5)
    ]
    for connection in stalled:
        connection.settimeout(2)
        connection.sendall(b"POST /jsonrpc HTTP/1.1\r\nHost: localhost")
    try:
        assert all(connection.recv(4096) == b"" for connection in stalled)
        status, response = _json_request(
            server.server_address[1],
            {"jsonrpc": "2.0", "method": "ping", "id": 1},
        )
    finally:
        for connection in stalled:
            connection.close()
        server.begin_shutdown()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)

    assert status == 200
    assert response["result"] is True
    assert methods.ping_calls == 1


def test_shared_listener_rejects_disallowed_ip_over_socket():
    identity = _IdentityContext()
    methods = _Methods(identity)
    server = FilteredXMLRPCServer(
        ("127.0.0.1", 0),
        allowed_ips_str="192.0.2.0/24",
        allow_none=True,
        logRequests=False,
    )
    server.register_instance(methods)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    try:
        with pytest.raises(
            (
                urllib.error.URLError,
                ConnectionResetError,
                http.client.RemoteDisconnected,
            )
        ):
            _json_request(
                server.server_address[1],
                {"jsonrpc": "2.0", "method": "ping", "id": 1},
            )
    finally:
        server.begin_shutdown()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)

    assert methods.ping_calls == 0


def test_jsonrpc_preserves_reserved_control_and_general_capacity():
    methods = _LaneMethods()
    server = FilteredXMLRPCServer(
        ("127.0.0.1", 0),
        allowed_ips_str="127.0.0.1",
        allow_none=True,
        logRequests=False,
    )
    server.register_instance(methods)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    port = server.server_address[1]
    results = []

    def call_slow(value):
        results.append(
            _json_request(
                port,
                {
                    "jsonrpc": "2.0",
                    "method": "slow",
                    "params": [value],
                    "id": value,
                },
            )
        )

    workers = [threading.Thread(target=call_slow, args=(value,)) for value in (1, 2, 3)]
    for worker in workers:
        worker.start()
    try:
        assert methods.three_started.wait(timeout=2)
        _, control = _json_request(
            port,
            {"jsonrpc": "2.0", "method": "ping", "id": "control"},
        )
        _, busy = _json_request(
            port,
            {"jsonrpc": "2.0", "method": "slow", "params": [4], "id": 4},
        )
    finally:
        methods.release.set()
        for worker in workers:
            worker.join(timeout=2)
        server.begin_shutdown()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)

    assert busy["error"] == {
        "code": -32000,
        "message": "Server busy",
        "data": {"reason": "server_busy", "lane": "general"},
    }
    assert control["result"] is True
    assert sorted(response["result"] for _, response in results) == [1, 2, 3]
