"""Compatibility import for the canonical GUI dispatch error."""

try:
    from ...dispatch.gui_errors import GuiDispatchError
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.gui_errors import GuiDispatchError

__all__ = ["GuiDispatchError"]
