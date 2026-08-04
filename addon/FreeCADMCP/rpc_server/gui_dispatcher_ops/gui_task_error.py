"""Compatibility import for the canonical GUI task error."""

try:
    from ...dispatch.gui_errors import GuiTaskError
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.gui_errors import GuiTaskError

__all__ = ["GuiTaskError"]
