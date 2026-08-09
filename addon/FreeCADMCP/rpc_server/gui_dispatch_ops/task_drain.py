"""Drain queued GUI-thread callables."""

from __future__ import annotations

import traceback
from typing import Any

import FreeCAD

from . import queue_state


def drain_task_queue() -> bool:
    """Drain queued tasks and return True when shutdown was requested."""
    while not queue_state.rpc_request_queue.empty():
        task = queue_state.rpc_request_queue.get()
        if task is queue_state.SHUTDOWN:
            return True
        try:
            task()
        except Exception as exc:
            FreeCAD.Console.PrintError(
                f"MCP RPC: unhandled exception in GUI task: {type(exc).__name__}: {exc}\n"
                f"{traceback.format_exc()}"
            )
    return False


def processing_ui_context() -> tuple[Any | None, Any | None]:
    import FreeCADGui
    from PySide import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance()
    try:
        status_bar = FreeCADGui.getMainWindow().statusBar()
    except Exception:
        status_bar = None
    if app is not None:
        app.setOverrideCursor(QtCore.Qt.WaitCursor)
    if status_bar is not None:
        status_bar.showMessage("MCP: processing…")
    return app, status_bar


def clear_processing_ui_context(app: Any | None, status_bar: Any | None) -> None:
    if app is not None:
        app.restoreOverrideCursor()
    if status_bar is not None:
        status_bar.clearMessage()
