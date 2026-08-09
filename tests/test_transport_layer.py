"""Behavior and compatibility contracts for the canonical transport layer."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from addon.FreeCADMCP.transport.ip_filter import (
    _parse_allowed_ips,
    validate_allowed_ips,
)
from addon.FreeCADMCP.transport.json_rpc_errors import json_rpc_error_from_result
from addon.FreeCADMCP.transport.json_rpc_transport import (
    JsonRpcError,
    JsonRpcTransport,
)
from addon.FreeCADMCP.transport.listener import (
    JsonRpcListener,
    xmlrpc_safe_response,
)
from addon.FreeCADMCP.transport.request_handler import JsonRpcRequestHandler
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit


def _close_listener(listener: JsonRpcListener) -> None:
    listener.server_close()


def _post_json(
    listener: JsonRpcListener,
    document: object,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any] | None]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{listener.server_address[1]}/jsonrpc",
        data=json.dumps(document, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        response = urllib.request.urlopen(request, timeout=2)
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return exc.code, json.loads(payload) if payload else None
    with response:
        payload = response.read()
        return response.status, json.loads(payload) if payload else None


def _running_listener(
    *,
    capture_request_identity: Callable[..., None] | None = None,
    clear_request_identity: Callable[[], None] | None = None,
) -> tuple[JsonRpcListener, threading.Thread]:
    listener = JsonRpcListener(
        ("127.0.0.1", 0),
        allowed_ips_str="127.0.0.1",
        capture_request_identity=capture_request_identity,
        clear_request_identity=clear_request_identity,
        allow_none=True,
        logRequests=False,
    )
    loop = threading.Thread(target=listener.serve_forever, daemon=True)
    loop.start()
    return listener, loop


def test_listener_constructor_injects_handler_transport_and_mapper_without_serving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatches: list[tuple[str, object]] = []
    factory_calls: list[tuple[object, object]] = []
    mapper = lambda result: None

    class Handler(JsonRpcRequestHandler):
        pass

    class FakeTransport:
        def __init__(self, dispatch, *, result_to_error):
            factory_calls.append((dispatch, result_to_error))
            self.shutdowns = 0

        def handle_bytes(self, _payload: bytes) -> bytes:
            raise AssertionError("construction must not dispatch")

        def begin_shutdown(self) -> None:
            self.shutdowns += 1

    def forbidden_thread(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("listener construction must not create a serve thread")

    monkeypatch.setattr(threading, "Thread", forbidden_thread)
    listener = JsonRpcListener(
        ("127.0.0.1", 0),
        requestHandler=Handler,
        transport_factory=FakeTransport,
        result_to_error=mapper,
        allow_none=True,
        logRequests=False,
    )
    try:
        assert listener.RequestHandlerClass is Handler
        assert len(factory_calls) == 1
        dispatch, installed_mapper = factory_calls[0]
        assert getattr(dispatch, "__self__", None) is listener
        assert getattr(dispatch, "__func__", None) is getattr(
            listener._dispatch_json_rpc, "__func__", None
        )
        assert installed_mapper is mapper
        assert dispatches == []
        assert listener._json_rpc_transport.shutdowns == 0
    finally:
        _close_listener(listener)


def test_listener_binds_requested_loopback_and_applies_ip_filter() -> None:
    listener = JsonRpcListener(
        ("127.0.0.1", 0),
        allowed_ips_str="127.0.0.1,::1/128",
        allow_none=True,
        logRequests=False,
    )
    try:
        host, port = listener.server_address[:2]
        assert host == "127.0.0.1"
        assert isinstance(port, int) and port > 0
        assert listener.verify_request(object(), ("127.0.0.1", 1000)) is True
        assert listener.verify_request(object(), ("203.0.113.9", 1000)) is False
    finally:
        _close_listener(listener)


def test_listener_bind_failure_does_not_construct_transport_or_leave_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed: list[bool] = []

    class FakeTransport:
        def __init__(self) -> None:
            self.shutdowns = 0

        def begin_shutdown(self) -> None:
            self.shutdowns += 1

    transports: list[FakeTransport] = []

    def factory(*_args: object, **_kwargs: object) -> object:
        constructed.append(True)
        transport = FakeTransport()
        transports.append(transport)
        return transport

    def fail_bind(self: object) -> None:
        raise OSError("address unavailable")

    monkeypatch.setattr("socketserver.TCPServer.server_bind", fail_bind)
    with pytest.raises(OSError, match="address unavailable"):
        JsonRpcListener(
            ("127.0.0.1", 0),
            transport_factory=factory,
            allow_none=True,
            logRequests=False,
        )

    # Construction may prepare the injected codec before the stdlib bind, but
    # must never retry it or start a request/serve worker after bind failure.
    assert len(constructed) <= 1
    assert all(transport.shutdowns == 1 for transport in transports)


def test_request_identity_callbacks_bracket_success_and_dispatch_failure() -> None:
    current = threading.local()
    events: list[tuple[str, object]] = []

    def capture(**identity: object) -> None:
        assert not hasattr(current, "identity")
        current.identity = identity
        events.append(("capture", identity))

    def clear() -> None:
        assert hasattr(current, "identity")
        events.append(("clear", current.identity))
        del current.identity

    listener, loop = _running_listener(
        capture_request_identity=capture,
        clear_request_identity=clear,
    )

    def identity() -> dict[str, object]:
        return dict(current.identity)

    def fail() -> None:
        raise RuntimeError("sensitive-dispatch-detail")

    listener.register_function(identity, "identity")
    listener.register_function(fail, "fail")
    headers = {
        "X-MCP-Instance-Id": "runtime-a",
        "X-MCP-Client": "pytest",
        "X-MCP-Pid": "42",
        "X-MCP-Request-Id": "request-a",
    }
    try:
        status, response = _post_json(
            listener,
            {"jsonrpc": "2.0", "method": "identity", "id": 1},
            headers=headers,
        )
        assert status == 200
        assert response is not None
        assert response["result"]["instance_id"] == "runtime-a"
        assert response["result"]["pid"] == 42

        status, response = _post_json(
            listener,
            {"jsonrpc": "2.0", "method": "fail", "id": 2},
            headers=headers,
        )
        assert status == 200
        assert response is not None
        assert response["error"] == {"code": -32603, "message": "Internal error"}
        assert "sensitive-dispatch-detail" not in json.dumps(response)

        request = urllib.request.Request(
            f"http://127.0.0.1:{listener.server_address[1]}/jsonrpc",
            data=b"{",
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as malformed_response:
            malformed = json.loads(malformed_response.read())
        assert malformed["error"] == {"code": -32700, "message": "Parse error"}
    finally:
        listener.begin_shutdown()
        listener.shutdown()
        listener.server_close()
        loop.join(timeout=2)

    assert [event for event, _value in events] == [
        "capture",
        "clear",
        "capture",
        "clear",
        "capture",
        "clear",
    ]
    assert events[0][1] is events[1][1]
    assert events[2][1] is events[3][1]
    assert events[4][1] is events[5][1]
    assert not hasattr(current, "identity")


def test_request_identity_ignores_all_legacy_document_authority_inputs() -> None:
    current = threading.local()

    def capture(**identity: object) -> None:
        current.identity = identity

    def clear() -> None:
        del current.identity

    listener, loop = _running_listener(
        capture_request_identity=capture,
        clear_request_identity=clear,
    )

    def identity(_payload: object) -> dict[str, object]:
        return dict(current.identity)

    listener.register_function(identity, "identity")
    headers = {
        "X-MCP-Instance-Id": "runtime-a",
        "X-MCP-Client": "pytest",
        "X-MCP-Pid": "42",
        "X-MCP-Host": "localhost",
        "X-MCP-Rpc-Port": "9876",
        "X-MCP-Request-Id": "request-a",
        "X-MCP-Session-Token": "auth-token",
        "X-MCP-Lease-Token": "legacy-lease-token",
        "X-MCP-Lease-Id": "legacy-lease-id",
        "X-MCP-Lease-Generation": "not-an-integer",
        "X-MCP-Document-Session-Id": "legacy-document-session",
        "X-MCP-Lease-Credentials": "not-json",
    }
    try:
        status, response = _post_json(
            listener,
            {
                "jsonrpc": "2.0",
                "method": "identity",
                "params": [{"lease_credentials": [{"token": "payload-secret"}]}],
                "id": 1,
            },
            headers=headers,
        )
        assert status == 200
        assert response == {
            "jsonrpc": "2.0",
            "result": {
                "instance_id": "runtime-a",
                "client": "pytest",
                "pid": 42,
                "host": "localhost",
                "rpc_port": 9876,
                "request_id": "request-a",
                "rpc_session_token": "auth-token",
            },
            "id": 1,
        }
    finally:
        listener.begin_shutdown()
        listener.shutdown()
        listener.server_close()
        loop.join(timeout=2)


def test_identity_callback_failures_are_suppressed_at_listener_boundary() -> None:
    clear_calls: list[bool] = []

    def capture(**_identity: object) -> None:
        raise RuntimeError("private-capture-detail")

    def clear() -> None:
        clear_calls.append(True)
        raise RuntimeError("private-clear-detail")

    listener, loop = _running_listener(
        capture_request_identity=capture,
        clear_request_identity=clear,
    )
    listener.register_function(lambda: True, "ping")
    try:
        status, response = _post_json(
            listener,
            {"jsonrpc": "2.0", "method": "ping", "id": 1},
        )
        assert status == 200
        assert response == {"jsonrpc": "2.0", "result": True, "id": 1}
    finally:
        listener.begin_shutdown()
        listener.shutdown()
        listener.server_close()
        loop.join(timeout=2)

    assert clear_calls == [True]


def test_begin_shutdown_rejects_new_dispatch_and_closes_cleanly() -> None:
    listener = JsonRpcListener(
        ("127.0.0.1", 0),
        allow_none=True,
        logRequests=False,
    )
    listener.register_function(lambda: True, "ping")
    listener.begin_shutdown()
    try:
        with pytest.raises(JsonRpcError) as captured:
            listener._dispatch_json_rpc("ping", ())
        assert captured.value.code == -32004
        assert captured.value.message == "Server stopping"
    finally:
        listener.server_close()


def test_server_close_cleans_socket_and_executor_when_injected_shutdown_fails() -> None:
    class FailingTransport:
        def begin_shutdown(self) -> None:
            raise RuntimeError("injected shutdown failed")

    listener = JsonRpcListener(
        ("127.0.0.1", 0),
        transport_factory=lambda *_args, **_kwargs: FailingTransport(),
        allow_none=True,
        logRequests=False,
    )
    executor = listener._handler_executor

    with pytest.raises(RuntimeError, match="injected shutdown failed"):
        listener.server_close()

    assert listener.socket.fileno() == -1
    assert executor._shutdown is True


def test_canonical_codec_preserves_frozen_error_mapping_and_wire_behavior() -> None:
    transport = JsonRpcTransport(
        lambda _method, _params: {
            "success": False,
            "error_code": "STALE_REVISION",
            "message": "Revision changed",
            "token": "secret-token",
        },
        result_to_error=json_rpc_error_from_result,
    )

    payload = transport.handle_bytes(
        b'{"jsonrpc":"2.0","method":"write","params":[],"id":7}'
    )
    assert payload is not None
    response = json.loads(payload)
    assert response["error"]["code"] == -32002
    assert response["error"]["data"]["token"] == "<redacted>"


def test_rpc_server_consumes_transport_authentication_and_replay_identities() -> None:
    bootstrap_unit_test_runtime()
    from addon.FreeCADMCP.rpc_server import rpc_server
    from addon.FreeCADMCP.transport import authentication, replay

    assert rpc_server.SessionManager is authentication.SessionManager
    assert rpc_server.load_profile_secret is authentication.load_profile_secret
    assert rpc_server.make_runtime_manifest is authentication.make_runtime_manifest
    assert rpc_server.RequestReplayCache is replay.RequestReplayCache


def test_legacy_codec_error_listener_and_ip_paths_are_exact_compatibility_aliases() -> None:
    from addon.FreeCADMCP.rpc_server import filtered_xmlrpc_server as legacy_listener
    from addon.FreeCADMCP.rpc_server import ip_filter as legacy_ip
    from addon.FreeCADMCP.rpc_server import json_rpc_errors as legacy_errors
    from addon.FreeCADMCP.rpc_server import json_rpc_transport as legacy_transport

    assert legacy_transport.JsonRpcError is JsonRpcError
    assert legacy_transport.JsonRpcTransport is JsonRpcTransport
    assert legacy_errors.json_rpc_error_from_result is json_rpc_error_from_result
    assert issubclass(legacy_listener.FilteredXMLRPCServer, JsonRpcListener)
    assert legacy_listener.validate_allowed_ips is validate_allowed_ips
    assert legacy_listener._parse_allowed_ips is _parse_allowed_ips
    assert legacy_listener.xmlrpc_safe_response is xmlrpc_safe_response
    assert legacy_ip.FilteredXMLRPCServer is legacy_listener.FilteredXMLRPCServer
    assert legacy_ip.validate_allowed_ips is validate_allowed_ips
    assert legacy_ip._parse_allowed_ips is _parse_allowed_ips


def test_legacy_ip_validation_behavior_is_unchanged() -> None:
    from addon.FreeCADMCP.rpc_server.ip_filter import (
        _parse_allowed_ips as legacy_parse,
    )
    from addon.FreeCADMCP.rpc_server.ip_filter import (
        validate_allowed_ips as legacy_validate,
    )

    value = "127.0.0.1,10.0.0.0/8"
    assert legacy_validate(value) == validate_allowed_ips(value)
    assert [str(item) for item in legacy_parse(value)] == [
        str(item) for item in _parse_allowed_ips(value)
    ]


def test_flat_addon_transport_and_legacy_shims_preserve_exact_identities() -> None:
    addon_root = Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP"
    script = f"""
import sys
sys.path.insert(0, {str(addon_root)!r})
from _shared.protocol.request_replay_cache import RequestReplayCache as CanonicalReplay
from _shared.protocol.session_manager import SessionManager as CanonicalSession
from rpc_server.filtered_xmlrpc_server import FilteredXMLRPCServer
from rpc_server.json_rpc_errors import json_rpc_error_from_result as legacy_error
from rpc_server.json_rpc_transport import JsonRpcError as LegacyError
from rpc_server.json_rpc_transport import JsonRpcTransport as LegacyTransport
from transport.authentication import SessionManager
from transport.json_rpc_errors import json_rpc_error_from_result
from transport.json_rpc_transport import JsonRpcError, JsonRpcTransport
from transport.listener import JsonRpcListener
from transport.replay import RequestReplayCache
assert LegacyError is JsonRpcError
assert LegacyTransport is JsonRpcTransport
assert legacy_error is json_rpc_error_from_result
assert issubclass(FilteredXMLRPCServer, JsonRpcListener)
assert SessionManager is CanonicalSession
assert RequestReplayCache is CanonicalReplay
"""

    completed = subprocess.run(
        [sys.executable, "-I", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
