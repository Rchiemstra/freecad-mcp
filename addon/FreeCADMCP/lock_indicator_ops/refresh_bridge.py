"""Queued refresh signal bridge for lock_indicator."""

from __future__ import annotations

from typing import Any


def refresh_bridge_type(qt_core: Any) -> type:
    class _RefreshBridge(qt_core.QObject):
        refresh_requested = qt_core.Signal()
        local_save_completed = qt_core.Signal(object)
        local_restore_completed = qt_core.Signal(object)

        @qt_core.Slot()
        def refresh_now(self) -> None:
            from .refresh import _refresh_lock_indicator_now

            _refresh_lock_indicator_now()

    return _RefreshBridge
