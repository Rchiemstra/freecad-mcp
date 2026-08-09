"""Compatibility surface for the canonical GUI dispatch layer."""

from PySide import QtCore, QtWidgets  # noqa: F401 - public test/adapter seam

try:
    from ..dispatch.gui_errors import (
        GuiBusyAfterTimeout,
        GuiDispatchError,
        GuiDispatchTimeout,
        GuiTaskError,
    )
    from ..dispatch.gui_outcome import GuiOutcome
    from ..dispatch.gui_request import GuiRequest
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.gui_errors import (
        GuiBusyAfterTimeout,
        GuiDispatchError,
        GuiDispatchTimeout,
        GuiTaskError,
    )
    from dispatch.gui_outcome import GuiOutcome
    from dispatch.gui_request import GuiRequest

from .gui_dispatcher_qt import GuiDispatcher

__all__ = [
    "GuiBusyAfterTimeout",
    "GuiDispatchError",
    "GuiDispatchTimeout",
    "GuiDispatcher",
    "GuiOutcome",
    "GuiRequest",
    "GuiTaskError",
]
