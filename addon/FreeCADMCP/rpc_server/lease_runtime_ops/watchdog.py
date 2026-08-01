"""Process-lifetime lease watchdog daemon."""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("FreeCADMCP.rpc_server")


def lease_watchdog_loop(
    interval_seconds: float = 2.0,
    stop_event: threading.Event | None = None,
    *,
    rpc_mod: Any,
) -> None:
    """Fence expired leases even when the owning MCP process has disappeared."""

    stop_event = stop_event or rpc_mod.lease_watchdog_stop
    while not stop_event.wait(float(interval_seconds)):
        service = rpc_mod.document_lease_service
        if service is None:
            continue
        try:
            expired = service.mark_expired_stale()
        except Exception:
            logger.exception("Document lease watchdog failed")
            continue
        if not expired:
            continue
        logger.warning("Marked expired document leases stale: %s", ", ".join(expired))
        try:
            from lock_indicator import refresh_lock_indicator

            # The indicator owns the Qt queued-signal hop; this thread never
            # accesses a widget directly.
            refresh_lock_indicator()
        except Exception:
            logger.debug("Could not queue lease indicator refresh", exc_info=True)


def ensure_lease_watchdog_running(interval_seconds: float = 2.0, *, rpc_mod: Any):
    """Start exactly one process-lifetime stale-expiry daemon."""

    with rpc_mod.lease_watchdog_lock:
        current = rpc_mod.lease_watchdog_thread
        if current is not None and current.is_alive():
            return current
        stop_event = threading.Event()
        thread = threading.Thread(
            target=rpc_mod._lease_watchdog_loop,
            args=(float(interval_seconds), stop_event),
            name="FreeCADMCP-LeaseWatchdog",
            daemon=True,
        )
        rpc_mod.lease_watchdog_stop = stop_event
        rpc_mod.lease_watchdog_thread = thread
        thread.start()
        return thread


def shutdown_document_lease_runtime(timeout: float = 3.0, *, rpc_mod: Any) -> bool:
    """Stop only the process-lifetime daemon during final addon teardown/tests.

    Lease/identity services and every active or foreign recovery record remain
    intact. Listener stop/restart must never call this helper.
    """

    with rpc_mod.lease_watchdog_lock:
        thread = rpc_mod.lease_watchdog_thread
        stop_event = rpc_mod.lease_watchdog_stop
        if thread is None:
            return True
        stop_event.set()
    if thread is not threading.current_thread():
        thread.join(timeout=max(0.0, float(timeout)))
    with rpc_mod.lease_watchdog_lock:
        if rpc_mod.lease_watchdog_thread is thread and not thread.is_alive():
            rpc_mod.lease_watchdog_thread = None
        return rpc_mod.lease_watchdog_thread is None
