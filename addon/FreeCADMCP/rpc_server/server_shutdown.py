"""Stop both RPC encodings and release worker/dispatcher resources."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger("FreeCADMCP.rpc_server")


def _fence_inflight_cancellations(rpc_mod: Any, cancelling_rpc: Any) -> None:
    cancellation_deadline = (
        time.monotonic() + rpc_mod.RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS
    )
    for inflight in rpc_mod.rpc_inflight_request_registry.request_cancel_all():
        try:
            remaining = max(0.0, cancellation_deadline - time.monotonic())
            fenced = cancelling_rpc._begin_request_cancellation(
                inflight, wait_timeout=remaining
            )
            if fenced is None:
                logger.error(
                    "Cancellation fence for request %s is still owned by "
                    "another phase; retaining its active lease/error fence",
                    inflight.request_id,
                )
        except Exception:
            logger.exception(
                "Could not fence request %s during RPC shutdown",
                inflight.request_id,
            )


def _run_listener_shutdown(server: Any, thread: Any, worker_manager: Any) -> threading.Event:
    completed = threading.Event()

    def _shutdown():
        try:
            server.begin_shutdown()
            if worker_manager is not None:
                worker_manager.stop(timeout=4.0)
            server.shutdown()
            server.server_close()
            if thread is not None:
                thread.join(timeout=2.0)
        finally:
            completed.set()

    threading.Thread(target=_shutdown, daemon=True).start()
    return completed


def _clear_rpc_runtime_state(rpc_mod: Any, dispatcher: Any) -> None:
    rpc_mod.rpc_server_instance = None
    rpc_mod.rpc_server_thread = None
    rpc_mod.gui_dispatcher = None
    rpc_mod.worker_manager = None
    rpc_mod.rpc_server_runtime_id = ""
    rpc_mod.rpc_server_started_at = ""
    rpc_mod.rpc_server_actual_endpoint = None
    rpc_mod.rpc_session_manager = None
    rpc_mod.rpc_runtime_manifest = None
    if dispatcher is not None:
        dispatcher.deleteLater()


def stop_rpc_server():
    from . import rpc_server as rpc_mod

    if not rpc_mod.rpc_server_instance:
        return "RPC Server was not running."

    rpc_mod.shutdown_requested.set()
    server = rpc_mod.rpc_server_instance
    thread = rpc_mod.rpc_server_thread
    worker_manager = rpc_mod.worker_manager
    cancelling_rpc = rpc_mod.FreeCADRPC()
    _fence_inflight_cancellations(rpc_mod, cancelling_rpc)
    if rpc_mod.gui_dispatcher is not None:
        rpc_mod.gui_dispatcher.stop_accepting()

    completed = _run_listener_shutdown(server, thread, worker_manager)
    completed.wait(timeout=2.5)
    dispatcher = rpc_mod.gui_dispatcher
    _clear_rpc_runtime_state(rpc_mod, dispatcher)
    logger.info("RPC Server stopped")
    if completed.is_set():
        return "RPC Server stopped."
    return "RPC Server shutdown is continuing in the background."
