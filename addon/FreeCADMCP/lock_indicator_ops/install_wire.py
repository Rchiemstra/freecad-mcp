from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from typing import Any

from . import state
from .refresh import _refresh_lock_indicator_now, refresh_lock_indicator


def wire_status_details_click(status: Any) -> None:
    def show_details() -> None:
        if state._shared_state.dock_widget is not None:
            state._shared_state.dock_widget.show()
            state._shared_state.dock_widget.raise_()

    status.clicked.connect(show_details)


def wire_refresh_timer(main: Any, qt_core: Any) -> None:
    timer = qt_core.QTimer(main)
    timer.setInterval(1000)
    timer.timeout.connect(_refresh_lock_indicator_now)
    timer.start()
    state._shared_state.refresh_timer = timer


def wire_gui_update_callback(
    set_gui_update_callback: Callable[[Callable[[], None]], None],
) -> None:
    with suppress(Exception):
        set_gui_update_callback(refresh_lock_indicator)


def mount_dock_widget(main: Any, dock: Any, qt_core: Any) -> None:
    try:
        main.addDockWidget(qt_core.Qt.RightDockWidgetArea, dock)
        dock.setFloating(False)
        state._shared_state.dock_widget = dock
    except Exception:
        state._shared_state.dock_widget = None
