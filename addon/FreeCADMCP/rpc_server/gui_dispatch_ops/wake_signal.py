"""Qt signal bridge for cross-thread GUI-task wakeup."""

from __future__ import annotations

from PySide import QtCore

from . import queue_state
from .process_gui_tasks import process_gui_tasks


class WakeSignal(QtCore.QObject):
    """Qt signal bridge for cross-thread GUI-task wakeup.

    Must be created on the GUI thread (``init_waker``). Emitting from the
    RPC thread is safe: Qt delivers the connection with ``QueuedConnection``,
    so the slot always fires in the GUI thread's event loop.
    """

    _sig = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._sig.connect(self._on_wake, QtCore.Qt.QueuedConnection)

    def wake(self) -> None:
        self._sig.emit()

    def _on_wake(self) -> None:
        process_gui_tasks(reschedule=False)


def init_waker() -> None:
    """Create the wake-signal bridge. Call once from the GUI thread."""
    queue_state.waker = WakeSignal()


def cleanup_waker() -> None:
    """Release the wake-signal bridge on server stop."""
    queue_state.waker = None
