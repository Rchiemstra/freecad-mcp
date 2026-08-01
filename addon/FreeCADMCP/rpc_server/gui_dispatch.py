"""GUI-thread task dispatch for the RPC server.

The XML-RPC server runs in its own thread. FreeCAD APIs that touch the GUI
or the document tree must run in the main GUI thread. This module owns the
queue that ferries wrapped callables onto the GUI thread and the helper that
RPC handlers use to invoke them.

Robustness and performance guarantees:

1. Per-call response queues: each ``dispatch_to_gui`` call owns its own
   ``queue.Queue``. A timeout in one call can never corrupt the response for
   a subsequent call.
2. Immediate wake via Qt signal: ``dispatch_to_gui`` emits a signal from the
   RPC thread; the GUI thread processes the task immediately rather than
   waiting for the next 500 ms heartbeat tick. The 500 ms heartbeat is kept
   only as a fallback.
3. Mouse-button guard: ``process_gui_tasks`` skips the current tick while
   mouse buttons are held so MCP tasks cannot interrupt 3D navigation drags.
4. Clean shutdown: the ``_SHUTDOWN`` sentinel sets a flag that suppresses the
   ``finally`` reschedule, so ``stop_rpc_server`` actually stops the loop.
5. Exception isolation: exceptions inside a task are caught, logged, and
   returned as error strings; they never kill the dispatch loop.
"""

from __future__ import annotations

# §3.3 compatibility shims — moved symbols keep their legacy import path.
from .gui_dispatch_ops import queue_state
from .gui_dispatch_ops import wake_signal as _wake_signal_module
from .gui_dispatch_ops.dispatch_to_gui import dispatch_to_gui  # noqa: F401
from .gui_dispatch_ops.flush_gui_events import flush_gui_events as _flush_gui_events  # noqa: F401
from .gui_dispatch_ops.process_gui_tasks import process_gui_tasks  # noqa: F401
from .gui_dispatch_ops.request_shutdown import request_shutdown  # noqa: F401

_WakeSignal = _wake_signal_module.WakeSignal
cleanup_waker = _wake_signal_module.cleanup_waker
init_waker = _wake_signal_module.init_waker
_SHUTDOWN = queue_state.SHUTDOWN
_rpc_request_queue = queue_state.rpc_request_queue


def __getattr__(name: str):
    if name == "_processing":
        return queue_state.processing
    if name == "_processing_since":
        return queue_state.processing_since
    if name == "_waker":
        return queue_state.waker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
