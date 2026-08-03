"""Phase 5 live-socket contracts for XML-RPC listener retirement."""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
import urllib.error
import urllib.request
import xmlrpc.client
from pathlib import Path

import pytest

from addon.FreeCADMCP._shared.protocol.json_rpc_client import (
    JSON_RPC_PROTOCOL_HEADER,
    JSON_RPC_PROTOCOL_VALUE,
)
from addon.FreeCADMCP.rpc_server import xmlrpc_identity_handler
from addon.FreeCADMCP.rpc_server.filtered_xmlrpc_server import FilteredXMLRPCServer

pytestmark = pytest.mark.unit

_CONTRACT_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "freecad_rpc_contract_snapshot.json"
)
_LISTENER_CONTRACT = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))[
    "listener_contract"
]
_DEPRECATION = _LISTENER_CONTRACT["post_phase5_deprecation"]
_NEGOTIATION = _LISTENER_CONTRACT["post_phase5_negotiation"]


class _IdentityContext:
    def set_request_identity(self, **_identity):
        return None

    def clear_request_identity(self):
        return None


class _Methods:
    def __init__(self):
        self.calls = []

    def ping(self):
        self.calls.append("ping")
        return True


@pytest.fixture
def live_server(monkeypatch):
    monkeypatch.setattr(
        xmlrpc_identity_handler,
        "_import_document_lock",
        lambda: _IdentityContext(),
    )
    methods = _Methods()
    server = FilteredXMLRPCServer(
        ("127.0.0.1", 0),
        allowed_ips_str="127.0.0.1",
        allow_none=True,
        logRequests=False,
    )
    server.register_instance(methods)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    try:
        yield server, methods
    finally:
        server.begin_shutdown()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)


def _post(port, path, body, *, headers=None, timeout=2):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "text/xml", **(headers or {})},
        )
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


@pytest.mark.parametrize("path", _DEPRECATION["paths"])
def test_xmlrpc_routes_return_deterministic_deprecation_without_dispatch(
    live_server, path
):
    server, methods = live_server
    request = xmlrpc.client.dumps((), methodname="ping").encode()

    status, headers, body = _post(server.server_address[1], path, request)

    assert status == _DEPRECATION["status"]
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert headers["Content-Length"] == str(len(body))
    for name, value in _DEPRECATION["headers"].items():
        assert headers[name] == value
    assert headers[JSON_RPC_PROTOCOL_HEADER] == JSON_RPC_PROTOCOL_VALUE
    assert json.loads(body) == _DEPRECATION["body"]
    assert methods.calls == []


def test_xmlrpc_deprecation_does_not_wait_for_declared_request_body(live_server):
    server, methods = live_server
    connection = socket.create_connection(server.server_address, timeout=2)
    connection.settimeout(2)
    try:
        connection.sendall(
            b"POST /RPC2 HTTP/1.1\r\nHost: localhost\r\n"
            b"Content-Type: text/xml\r\nContent-Length: 1000000\r\n\r\n<"
        )
        response = connection.recv(4096)
    finally:
        connection.close()

    assert b" 410 Gone\r\n" in response
    assert b"Content-Length: 1000000" not in response
    assert methods.calls == []


def test_malformed_http_is_rejected_without_handler_traceback(live_server, capsys):
    server, methods = live_server
    connection = socket.create_connection(server.server_address, timeout=2)
    connection.settimeout(2)
    try:
        connection.sendall(b"BROKEN\r\n\r\n")
        response = connection.recv(4096)
    finally:
        connection.close()

    assert b"Error code: 400" in response
    assert "Traceback" not in capsys.readouterr().err
    assert methods.calls == []


def test_jsonrpc_path_remains_live_after_xmlrpc_retirement(live_server):
    server, methods = live_server
    payload = json.dumps({"jsonrpc": "2.0", "method": "ping", "id": 7}).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}/jsonrpc",
        data=payload,
        headers={
            "Content-Type": "application/json",
            JSON_RPC_PROTOCOL_HEADER: JSON_RPC_PROTOCOL_VALUE,
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=2) as response:
        result = json.loads(response.read())
        protocol = response.headers[JSON_RPC_PROTOCOL_HEADER]

    assert response.status == 200
    assert result == {"jsonrpc": "2.0", "id": 7, "result": True}
    assert protocol == JSON_RPC_PROTOCOL_VALUE
    assert methods.calls == ["ping"]


@pytest.mark.parametrize(
    ("document", "expected_status"),
    [
        ({"jsonrpc": "2.0", "method": "ping"}, 204),
        ({"jsonrpc": "1.0", "method": "ping", "id": 1}, 200),
    ],
)
def test_jsonrpc_notification_and_error_advertise_protocol(
    live_server, document, expected_status
):
    server, _methods = live_server
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_address[1], timeout=2
    )
    try:
        connection.request(
            "POST",
            "/jsonrpc",
            body=json.dumps(document).encode(),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        response.read()
    finally:
        connection.close()

    assert response.status == expected_status
    assert response.headers[JSON_RPC_PROTOCOL_HEADER] == JSON_RPC_PROTOCOL_VALUE


def test_jsonrpc_mismatched_protocol_is_bounded_and_never_dispatched(live_server):
    server, methods = live_server
    status, headers, body = _post(
        server.server_address[1],
        "/jsonrpc",
        b'{"jsonrpc":"2.0","method":"ping","id":1}',
        headers={JSON_RPC_PROTOCOL_HEADER: "jsonrpc-9.9"},
    )

    assert status == _NEGOTIATION["mismatch"]["status"]
    assert headers[JSON_RPC_PROTOCOL_HEADER] == JSON_RPC_PROTOCOL_VALUE
    assert headers["Content-Length"] == str(len(body))
    assert json.loads(body) == _NEGOTIATION["mismatch"]["response"]
    assert methods.calls == []


@pytest.mark.parametrize(
    "values",
    [
        (JSON_RPC_PROTOCOL_VALUE, "incompatible"),
        ("incompatible", JSON_RPC_PROTOCOL_VALUE),
        (JSON_RPC_PROTOCOL_VALUE, JSON_RPC_PROTOCOL_VALUE),
    ],
)
def test_jsonrpc_duplicate_protocol_headers_reject_before_body_or_dispatch(
    live_server, values
):
    server, methods = live_server
    connection = socket.create_connection(server.server_address, timeout=2)
    connection.settimeout(2)
    request = (
        b"POST /jsonrpc HTTP/1.1\r\nHost: localhost\r\n"
        + f"{JSON_RPC_PROTOCOL_HEADER}: {values[0]}\r\n".encode()
        + f"{JSON_RPC_PROTOCOL_HEADER}: {values[1]}\r\n".encode()
        + b"Content-Type: application/json\r\n"
        b"Content-Length: 1000000\r\n\r\n{"
    )
    try:
        connection.sendall(request)
        response = connection.recv(4096)
    finally:
        connection.close()

    assert b" 409 Conflict\r\n" in response
    assert JSON_RPC_PROTOCOL_HEADER.encode() in response
    assert methods.calls == []


@pytest.mark.parametrize(
    "framing_headers",
    [
        b"Content-Length: 43\r\nContent-Length: 43\r\n",
        b"Content-Length: +43\r\n",
        b"Content-Length: 4_3\r\n",
        b"Content-Length: " + (b"9" * 5000) + b"\r\n",
        b"Transfer-Encoding: chunked\r\nContent-Length: 43\r\n",
        b"Transfer-Encoding: chunked\r\nTransfer-Encoding: identity\r\n",
    ],
)
def test_jsonrpc_rejects_ambiguous_or_noncanonical_request_framing(
    live_server, framing_headers
):
    server, methods = live_server
    connection = socket.create_connection(server.server_address, timeout=2)
    connection.settimeout(2)
    try:
        connection.sendall(
            b"POST /jsonrpc HTTP/1.1\r\nHost: localhost\r\n"
            + framing_headers
            + b"\r\n"
        )
        response = connection.recv(4096)
    finally:
        connection.close()

    assert b" 400 " in response
    assert methods.calls == []


def test_jsonrpc_request_wall_clock_deadline_rejects_slow_drip(live_server):
    server, methods = live_server
    server.json_rpc_read_timeout_seconds = 0.1
    body = b'{"jsonrpc":"2.0","method":"ping","id":1}'
    connection = socket.create_connection(server.server_address, timeout=2)
    connection.settimeout(2)
    started = time.monotonic()
    try:
        connection.sendall(
            b"POST /jsonrpc HTTP/1.1\r\nHost: localhost\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\n\r\n"
        )
        for byte in body:
            try:
                connection.sendall(bytes([byte]))
            except OSError:
                break
            time.sleep(0.02)
        response = connection.recv(4096)
    finally:
        connection.close()

    assert time.monotonic() - started < 1.0
    assert b" 408 " in response or response == b""
    assert methods.calls == []


def test_ip_filter_preserves_private_parser_import_path():
    from addon.FreeCADMCP.rpc_server import filtered_xmlrpc_server, ip_filter

    assert ip_filter._parse_allowed_ips is filtered_xmlrpc_server._parse_allowed_ips


def test_xmlrpc_deprecation_preserves_ip_filter(live_server):
    server, methods = live_server
    server._allowed_networks = ()
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}/RPC2",
        data=b"<methodCall/>",
        method="POST",
    )

    with pytest.raises(
        (urllib.error.URLError, ConnectionResetError, http.client.RemoteDisconnected)
    ):
        urllib.request.urlopen(request, timeout=2)

    assert methods.calls == []


def test_direct_legacy_marshaling_hook_cannot_dispatch(live_server):
    server, methods = live_server
    request = xmlrpc.client.dumps((), methodname="ping").encode()

    response = server._marshaled_dispatch(request)

    assert json.loads(response) == _DEPRECATION["body"]
    assert methods.calls == []
