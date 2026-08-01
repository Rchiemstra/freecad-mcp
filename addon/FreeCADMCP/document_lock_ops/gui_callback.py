from __future__ import annotations

import contextlib
from collections.abc import Callable

_gui_update_callback: Callable[[], None] | None = None

_observer_registered = False


def set_gui_update_callback(callback: Callable[[], None] | None) -> None:
    global _gui_update_callback
    _gui_update_callback = callback


def _notify_gui() -> None:
    cb = _gui_update_callback
    if cb is not None:
        with contextlib.suppress(Exception):
            cb()
