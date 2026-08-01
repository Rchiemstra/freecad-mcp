"""Event-driven, per-request dispatch onto FreeCAD's Qt GUI thread."""

from __future__ import annotations

# §3.3 compatibility shims — moved symbols keep their legacy import path.
from PySide import QtCore, QtWidgets  # noqa: F401

from .gui_dispatcher_ops.gui_busy_after_timeout import GuiBusyAfterTimeout  # noqa: F401
from .gui_dispatcher_ops.gui_dispatch_error import GuiDispatchError  # noqa: F401
from .gui_dispatcher_ops.gui_dispatch_timeout import GuiDispatchTimeout  # noqa: F401
from .gui_dispatcher_ops.gui_dispatcher_impl import GuiDispatcher  # noqa: F401
from .gui_dispatcher_ops.gui_outcome import GuiOutcome  # noqa: F401
from .gui_dispatcher_ops.gui_request import GuiRequest  # noqa: F401
from .gui_dispatcher_ops.gui_task_error import GuiTaskError  # noqa: F401
