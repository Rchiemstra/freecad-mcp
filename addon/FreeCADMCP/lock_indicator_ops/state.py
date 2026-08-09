"""Mutable GUI widget handles shared by refresh and install."""

from __future__ import annotations

from typing import Any

from .module_aliases import install_module_aliases

_installed = False
_status_widget = None
_dock_widget = None
_refresh_timer = None
_refresh_bridge = None
_deterred_actions: dict[int, Any] = {}


class _StateAccess:
    """Temporary Phase 17 adapter over the inventoried module-owned state."""

    __slots__ = ()

    @property
    def installed(self) -> bool:
        return _installed

    @installed.setter
    def installed(self, value: bool) -> None:
        global _installed
        _installed = value

    @property
    def status_widget(self) -> Any:
        return _status_widget

    @status_widget.setter
    def status_widget(self, value: Any) -> None:
        global _status_widget
        _status_widget = value

    @property
    def dock_widget(self) -> Any:
        return _dock_widget

    @dock_widget.setter
    def dock_widget(self, value: Any) -> None:
        global _dock_widget
        _dock_widget = value

    @property
    def refresh_timer(self) -> Any:
        return _refresh_timer

    @refresh_timer.setter
    def refresh_timer(self, value: Any) -> None:
        global _refresh_timer
        _refresh_timer = value

    @property
    def refresh_bridge(self) -> Any:
        return _refresh_bridge

    @refresh_bridge.setter
    def refresh_bridge(self, value: Any) -> None:
        global _refresh_bridge
        _refresh_bridge = value

    @property
    def deterred_actions(self) -> dict[int, Any]:
        return _deterred_actions


_shared_state = _StateAccess()


install_module_aliases(__name__)
