"""Narrow GUI observer: edit-mode entry/exit, not camera or selection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .app_observer import LeaseObserver


class LeaseGuiObserver:
    """Narrow GUI observer: edit-mode entry/exit, not camera or selection."""

    def __init__(self, app_observer: LeaseObserver) -> None:
        self._app_observer = app_observer

    def slotInEdit(self, view_provider: Any) -> Any | None:
        return self._app_observer._handle(view_provider, "GUI edit-mode entry")

    def slotResetEdit(self, view_provider: Any) -> Any | None:
        return self._app_observer._handle(view_provider, "GUI edit-mode exit")
