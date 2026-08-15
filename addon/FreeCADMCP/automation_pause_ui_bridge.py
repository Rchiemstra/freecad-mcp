"""Neutral, local-only notification hook for automation-pause presentation.

The runtime pause gate may request a visual refresh, but it must not import a
Document Lock implementation.  The locally installed GUI supplies the queued
callback after its Qt bridge exists; RPC code sees only this dependency-neutral
handoff.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from threading import RLock

_lock = RLock()
_refresh_callback: Callable[[], None] | None = None


def set_local_pause_refresh(callback: Callable[[], None] | None) -> None:
    """Install a local GUI-thread queue callback; never exposed through RPC."""

    global _refresh_callback
    with _lock:
        _refresh_callback = callback


def request_local_pause_refresh() -> None:
    """Best-effort refresh request without importing or touching widgets."""

    with _lock:
        callback = _refresh_callback
    if callback is not None:
        with suppress(Exception):
            callback()


__all__ = ["request_local_pause_refresh", "set_local_pause_refresh"]
