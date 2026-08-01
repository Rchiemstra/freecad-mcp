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


install_module_aliases(__name__)
