"""Compatibility import for the canonical GUI dispatch timeout."""

try:
    from ...dispatch.gui_errors import GuiDispatchTimeout
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.gui_errors import GuiDispatchTimeout

__all__ = ["GuiDispatchTimeout"]
