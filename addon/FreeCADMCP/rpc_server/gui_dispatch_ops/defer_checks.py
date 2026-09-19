"""Defer checks for legacy GUI task processing."""

from __future__ import annotations

from PySide import QtCore, QtWidgets

from . import queue_state

try:
    from ...dispatch.gui_block_state import clear_gui_block, note_blocking_widget
except ImportError:  # pragma: no cover - flat addon import path
    from dispatch.gui_block_state import clear_gui_block, note_blocking_widget


def should_defer_gui_processing() -> bool:
    if queue_state.rpc_request_queue.empty():
        return True
    if QtWidgets.QApplication.mouseButtons() != QtCore.Qt.NoButton:
        return True
    popup = QtWidgets.QApplication.activePopupWidget()
    if popup is not None:
        note_blocking_widget("popup", popup)
        return True
    modal = QtWidgets.QApplication.activeModalWidget()
    if modal is not None:
        note_blocking_widget("modal dialog", modal)
        return True
    clear_gui_block()
    return False
