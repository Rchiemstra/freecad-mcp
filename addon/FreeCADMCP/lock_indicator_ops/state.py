"""Mutable GUI widget handles shared by refresh and install."""

from __future__ import annotations

from typing import Any

_installed = False
_status_widget = None
_dock_widget = None
_refresh_timer = None
_refresh_bridge = None
_deterred_actions: dict[int, Any] = {}
