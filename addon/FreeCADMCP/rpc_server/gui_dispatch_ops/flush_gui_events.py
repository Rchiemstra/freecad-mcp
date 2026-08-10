"""Flush pending Qt events after GUI-thread work."""

from __future__ import annotations

import FreeCADGui
from PySide import QtCore, QtWidgets


def flush_gui_events(delay_ms: int = 20) -> None:
    try:
        update = getattr(FreeCADGui, "updateGui", None)
        if callable(update):
            update()
    except Exception:
        pass
    app = QtWidgets.QApplication.instance()
    if app is None:
        return

    # ExcludeUserInputEvents: skip mouse/keyboard events to avoid re-entrancy
    # with ongoing navigation. ExcludeSocketNotifiers keeps network I/O out.
    flags = (
        QtCore.QEventLoop.ExcludeUserInputEvents
        | QtCore.QEventLoop.ExcludeSocketNotifiers
    )
    try:
        app.processEvents(flags, delay_ms)
        if delay_ms > 0:
            QtCore.QThread.msleep(delay_ms)
            app.processEvents(flags, delay_ms)
    except Exception:
        pass
