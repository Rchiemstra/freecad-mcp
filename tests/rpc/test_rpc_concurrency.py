"""Bounded JSON-RPC request concurrency tests."""

from __future__ import annotations

import json
import threading
import urllib.request

import FreeCAD
import FreeCADGui

if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server.rpc_server import FilteredXMLRPCServer


def _json_request(port, method, params=None, *, request_id=1):
    document = {"jsonrpc": "2.0", "method": method, "id": request_id}
    if params is not None:
        document["params"] = params
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/jsonrpc",
        data=json.dumps(document, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.loads(response.read())


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
        ("127.0.0.1", 0),
        allowed_ips_str="127.0.0.1",
        allow_none=True,
        logRequests=False,
    )
    server.register_instance(methods)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    port = server.server_address[1]
    slow_result = []

    def call_slow():
        slow_result.append(_json_request(port, "slow", request_id="slow"))

    slow_thread = threading.Thread(target=call_slow)
    slow_thread.start()
    try:
        assert methods.started.wait(timeout=2)
        assert _json_request(port, "ping", request_id="ping")["result"] is True
    finally:
        methods.release.set()
        slow_thread.join(timeout=2)
        server.begin_shutdown()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)
    assert slow_result == [{"jsonrpc": "2.0", "id": "slow", "result": True}]


def test_control_plane_remains_available_when_general_lane_is_saturated():
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
    calls = []

    def call_slow(request_id):
        calls.append(_json_request(port, "slow", request_id=request_id))

    workers = [
        threading.Thread(target=call_slow, args=(request_id,))
        for request_id in range(3)
    ]
    for worker in workers:
        worker.start()
    try:
        assert methods.three_started.wait(timeout=2)
        assert _json_request(port, "ping", request_id="ping")["result"] is True
        assert (
            _json_request(port, "get_worker_status", request_id="status")["result"][
                "active_job_id"
            ]
            == "active"
        )
        assert _json_request(
            port, "cancel_worker_job", ["pending"], request_id="cancel-pending"
        )["result"]["success"] is True
        assert _json_request(
            port, "cancel_worker_job", ["active"], request_id="cancel-active"
        )["result"]["success"] is True
        assert (
            _json_request(port, "shutdown_rpc_server", request_id="shutdown")[
                "result"
            ]["state"]
            == "stopping"
        )
        busy = _json_request(port, "slow", request_id="busy")
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
    assert sorted(response["id"] for response in calls) == [0, 1, 2]
    assert all(response["result"] is True for response in calls)


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

    def call_slow(request_id):
        _json_request(port, "slow", request_id=request_id)

    for request_id in range(3):
        worker = threading.Thread(target=call_slow, args=(request_id,))
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
        result = _json_request(
            port,
            "invoke_v2_control",
            [envelope],
            request_id="control-envelope",
        )["result"]
        assert result == {
            "success": True,
            "target": "cancel_request",
            "request_id": request_id,
        }
        busy = _json_request(port, "slow", request_id="busy")
        assert busy["error"]["code"] == -32000
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


def test_large_save_metadata_round_trips_as_json_integers():
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
        result = _json_request(
            server.server_address[1],
            "get_save_result_with_nanoseconds",
            request_id="wide-integers",
        )["result"]
        assert result == {
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
        assert result["success"] is True
        assert isinstance(result["generation"], int)
        assert result["save"]["verified"] is True
    finally:
        server.begin_shutdown()
        server.shutdown()
        server.server_close()
        loop.join(timeout=2)
