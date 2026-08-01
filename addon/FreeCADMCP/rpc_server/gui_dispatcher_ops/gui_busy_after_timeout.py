"""Error when a timed-out request still occupies the GUI thread."""

from __future__ import annotations

from .gui_dispatch_error import GuiDispatchError


class GuiBusyAfterTimeout(GuiDispatchError):
    """A timed-out request is still occupying FreeCAD's GUI thread."""

    error_code = "GUI_BUSY_AFTER_TIMEOUT"
