"""Qt ownership adapter for the standard-library GUI dispatch core."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide import QtCore

try:  # Installed add-on package.
    from ..dispatch.gui_core import GuiDispatchCore
    from ..dispatch.gui_outcome import GuiOutcome
except ImportError:  # Flat FreeCAD add-on import (``import rpc_server``).
    from dispatch.gui_core import GuiDispatchCore
    from dispatch.gui_outcome import GuiOutcome
from .gui_dispatcher_ops.navigation_guards import gui_busy_for_3d_navigation
from .telemetry import emit as emit_telemetry


class GuiDispatcher(QtCore.QObject):
    """Bind Qt thread ownership and queued wakeups to ``GuiDispatchCore``."""

    wake_requested = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._core = GuiDispatchCore(
            is_gui_thread=lambda: QtCore.QThread.currentThread() == self.thread(),
            wake_gui=self.wake_requested.emit,
            schedule_wake=lambda delay_ms, callback: QtCore.QTimer.singleShot(
                delay_ms,
                callback,
            ),
            gui_busy=gui_busy_for_3d_navigation,
            emit_telemetry=emit_telemetry,
        )
        try:
            queued = QtCore.Qt.ConnectionType.QueuedConnection
        except AttributeError:
            queued = QtCore.Qt.QueuedConnection
        self.wake_requested.connect(self._drain_one, queued)

    def submit(
        self,
        callable_: Callable[[], Any],
        timeout: float | None,
        *,
        request_id: str | None = None,
        session_id: str | None = None,
        on_complete: Callable[[str, GuiOutcome], None] | None = None,
    ) -> Any:
        return self._core.submit(
            callable_,
            timeout,
            request_id=request_id,
            session_id=session_id,
            on_complete=on_complete,
        )

    def cancel_request(self, session_id: str, request_id: str) -> str:
        return self._core.cancel_request(session_id, request_id)

    @QtCore.Slot()
    def _drain_one(self) -> None:
        self._core.drain_one()

    def stop_accepting(self) -> None:
        self._core.stop_accepting()

    @property
    def pending_count(self) -> int:
        return self._core.pending_count
