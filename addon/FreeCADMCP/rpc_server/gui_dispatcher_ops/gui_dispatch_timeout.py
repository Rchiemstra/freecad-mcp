"""Timeout error for GUI dispatch."""

from __future__ import annotations

from .gui_dispatch_error import GuiDispatchError


class GuiDispatchTimeout(GuiDispatchError):
    """The GUI did not complete a request before its caller timed out."""
