"""Post shutdown sentinel for legacy GUI dispatch."""

from __future__ import annotations

from . import queue_state


def request_shutdown() -> None:
    """Post the sentinel so the next dispatch tick exits without rescheduling."""
    queue_state.rpc_request_queue.put(queue_state.SHUTDOWN)
