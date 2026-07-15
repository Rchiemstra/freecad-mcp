"""Full RPC server shutdown/restart with active and pending worker calls."""

from __future__ import annotations

import threading
import time
import xmlrpc.client

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
FreeCADGui = pytest.importorskip("FreeCADGui")
from PySide import QtCore

if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server import rpc_server


pytestmark = pytest.mark.e2e


def _app():
    return QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])


def _pump_until(app, predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate()


def _call(port, method, *args):
    with xmlrpc.client.ServerProxy(
        f"http://127.0.0.1:{port}", allow_none=True
    ) as client:
        return getattr(client, method)(*args)


def test_full_server_shutdown_rejects_draining_work_and_restarts(monkeypatch):
    app = _app()
    monkeypatch.setattr(rpc_server.QtWidgets.QApplication, "instance", lambda: app)
    doc = FreeCAD.newDocument("RPCLifecycle")
    doc.addObject("Part::Box", "Box")
    doc.recompute()
    worker_results = []
    worker_threads = []
    try:
        assert "started" in rpc_server.start_rpc_server(port=0).lower()
        old_server = rpc_server.rpc_server_instance
        port = old_server.server_address[1]
        assert _call(port, "ping") is True

        for index in range(3):
            code = "import time; time.sleep(60)" if index == 0 else f"print({index})"
            thread = threading.Thread(
                target=lambda payload=code: worker_results.append(
                    _call(
                        port,
                        "execute_code",
                        payload,
                        {
                            "document": doc.Name,
                            "read_only": True,
                            "execution_mode": "worker",
                            "timeout_seconds": 120,
                        },
                    )
                )
            )
            thread.start()
            worker_threads.append(thread)

        _pump_until(
            app,
            lambda: rpc_server.worker_manager is not None
            and rpc_server.worker_manager.status()["queue_depth"] == 2,
        )
        started = time.monotonic()
        rpc_server.stop_rpc_server()
        shutdown_duration = time.monotonic() - started
        assert shutdown_duration < 3.0
        assert old_server._accepting_requests is False
        with pytest.raises(OSError):
            _call(port, "ping")
        for thread in worker_threads:
            thread.join(timeout=10)
            assert not thread.is_alive()
        codes = sorted(result["error_code"] for result in worker_results)
        assert codes.count("server_stopping") == 2
        assert codes.count("worker_cancelled") == 1

        assert "started" in rpc_server.start_rpc_server(port=0).lower()
        new_port = rpc_server.rpc_server_instance.server_address[1]
        assert _call(new_port, "ping") is True
        gui_result = []
        gui_thread = threading.Thread(
            target=lambda: gui_result.append(
                _call(new_port, "list_documents")
            )
        )
        gui_thread.start()
        _pump_until(app, lambda: not gui_thread.is_alive())
        assert doc.Name in gui_result[0]

        recovered = []
        recovered_thread = threading.Thread(
            target=lambda: recovered.append(
                _call(
                    new_port,
                    "execute_code",
                    "print('restart worker ok')",
                    {
                        "document": doc.Name,
                        "read_only": True,
                        "execution_mode": "worker",
                    },
                )
            )
        )
        recovered_thread.start()
        _pump_until(app, lambda: not recovered_thread.is_alive())
        assert recovered[0]["success"] is True
        assert "restart worker ok" in recovered[0]["message"]
    finally:
        if rpc_server.rpc_server_instance is not None:
            rpc_server.stop_rpc_server()
        for thread in worker_threads:
            thread.join(timeout=1)
        FreeCAD.closeDocument(doc.Name)
