"""Bounded XML-RPC request concurrency tests."""

from __future__ import annotations

import threading
import xmlrpc.client

import pytest

import FreeCADGui
import FreeCAD


if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server.rpc_server import FilteredXMLRPCServer


class _ConcurrentMethods:
    def __init__(self):
        self.started = threading.Event()
        self.three_started = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()
        self._active = 0

    def slow(self):
        with self._lock:
            self._active += 1
            if self._active == 3:
                self.three_started.set()
        self.started.set()
        try:
            self.release.wait(timeout=5)
            return True
        finally:
            with self._lock:
                self._active -= 1

    def ping(self):
        return True

    def get_worker_status(self):
        return {"active_job_id": "active", "pending_job_ids": ["pending"]}

    def cancel_worker_job(self, job_id):
        return {"success": job_id in {"active", "pending"}, "job_id": job_id}

    def shutdown_rpc_server(self):
        return {"success": True, "state": "stopping"}

    def invoke_v2_control(self, envelope):
        return {
            "success": True,
            "target": envelope.get("method"),
            "request_id": envelope.get("request_id"),
        }

    def get_save_result_with_nanoseconds(self):
        return {
            "success": True,
            "generation": 7,
            "baseline": {
                "mtime_ns": 9_223_372_036_854_775_000,
                "size": 5_000_000_000,
            },
            "save": {
                "previous_mtime_ns": -9_223_372_036_854_775_000,
                "verified": True,
            },
        }


def test_ping_runs_while_another_handler_is_occupied():
    methods = _ConcurrentMethods()
    server = FilteredXMLRPCServer(
        ("127.0.0.1", 0), allowed_ips_str="127.0.0.1", allow_none=True, logRequests=False
    )
    server.register_instance(methods)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    port = server.server_address[1]
    slow_result = []

    def call_slow():
        with xmlrpc.client.ServerProxy(f"http://127.0.0.1:{port}") as client:
            slow_result.append(client.slow())

    slow_thread = threading.Thread(target=call_slow)
    slow_thread.start()
    try:
        assert methods.started.wait(timeout=2)
        with xmlrpc.client.ServerProxy(f"http://127.0.0.1:{port}") as client:
            assert client.ping() is True
    finally:
        methods.release.set()
        slow_thread.join(timeout=2)
        server.begin_shutdown()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)
    assert slow_result == [True]


def test_control_plane_remains_available_when_general_lane_is_saturated():
    methods = _ConcurrentMethods()
    server = FilteredXMLRPCServer(
        ("127.0.0.1", 0), allowed_ips_str="127.0.0.1", allow_none=True, logRequests=False
    )
    server.register_instance(methods)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    port = server.server_address[1]
    calls = []

    def call_slow():
        with xmlrpc.client.ServerProxy(f"http://127.0.0.1:{port}") as client:
            calls.append(client.slow())

    workers = [threading.Thread(target=call_slow) for _ in range(3)]
    for worker in workers:
        worker.start()
    try:
        assert methods.three_started.wait(timeout=2)
        with xmlrpc.client.ServerProxy(f"http://127.0.0.1:{port}") as client:
            assert client.ping() is True
            assert client.get_worker_status()["active_job_id"] == "active"
            assert client.cancel_worker_job("pending")["success"] is True
            assert client.cancel_worker_job("active")["success"] is True
            assert client.shutdown_rpc_server()["state"] == "stopping"
            with pytest.raises(xmlrpc.client.Fault, match="server_busy: general") as exc:
                client.slow()
            assert exc.value.faultCode == 503
    finally:
        methods.release.set()
        for worker in workers:
            worker.join(timeout=2)
        server.begin_shutdown()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)
    assert calls == [True] * 3


def test_v2_control_envelope_uses_reserved_lane_while_mutations_are_saturated():
    methods = _ConcurrentMethods()
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
    workers = []

    def call_slow():
        with xmlrpc.client.ServerProxy(f"http://127.0.0.1:{port}") as client:
            client.slow()

    for _ in range(3):
        worker = threading.Thread(target=call_slow)
        worker.start()
        workers.append(worker)
    try:
        assert methods.three_started.wait(timeout=2)
        request_id = "11111111-1111-4111-8111-111111111111"
        envelope = {
            "protocol_version": 2,
            "request_id": request_id,
            "session_token": "redacted-test-session",
            "method": "cancel_request",
            "params": {"target_request_id": request_id},
            "lease_credentials": [],
        }
        with xmlrpc.client.ServerProxy(f"http://127.0.0.1:{port}") as client:
            result = client.invoke_v2_control(envelope)
            assert result == {
                "success": True,
                "target": "cancel_request",
                "request_id": request_id,
            }
            with pytest.raises(xmlrpc.client.Fault, match="server_busy: general"):
                client.slow()
    finally:
        methods.release.set()
        for worker in workers:
            worker.join(timeout=2)
        server.begin_shutdown()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)


def test_rejected_connection_uses_python_logging_not_freecad_console(monkeypatch):
    monkeypatch.setattr(
        FreeCAD.Console,
        "PrintWarning",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("background request used FreeCAD.Console")
        ),
    )
    server = FilteredXMLRPCServer(
        ("127.0.0.1", 0), allowed_ips_str="127.0.0.1", allow_none=True
    )
    try:
        assert server.verify_request(None, ("192.0.2.1", 1)) is False
    finally:
        server.server_close()


def test_large_save_metadata_is_sanitized_at_xmlrpc_response_boundary():
    methods = _ConcurrentMethods()
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
        with xmlrpc.client.ServerProxy(
            f"http://127.0.0.1:{server.server_address[1]}", allow_none=True
        ) as client:
            result = client.get_save_result_with_nanoseconds()
        assert result == {
            "success": True,
            "generation": 7,
            "baseline": {
                "mtime_ns": "9223372036854775000",
                "size": "5000000000",
            },
            "save": {
                "previous_mtime_ns": "-9223372036854775000",
                "verified": True,
            },
        }
        assert result["success"] is True
        assert isinstance(result["generation"], int)
        assert result["save"]["verified"] is True
    finally:
        server.begin_shutdown()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)
