"""Defer checks for legacy GUI task processing."""

from __future__ import annotations

from PySide import QtCore, QtWidgets

from . import queue_state


def should_defer_gui_processing() -> bool:
    if queue_state.rpc_request_queue.empty():
        return True
    if QtWidgets.QApplication.mouseButtons() != QtCore.Qt.NoButton:
        return True
    if QtWidgets.QApplication.activePopupWidget() is not None:
        return True
    return QtWidgets.QApplication.activeModalWidget() is not None
