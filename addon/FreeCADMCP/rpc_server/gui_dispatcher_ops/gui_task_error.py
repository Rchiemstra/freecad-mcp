"""Error raised when a GUI-thread callable fails."""

from __future__ import annotations

from .gui_dispatch_error import GuiDispatchError


class GuiTaskError(GuiDispatchError):
    """A callable raised while executing on the GUI thread."""

    error_code = "GUI_TASK_FAILED"
