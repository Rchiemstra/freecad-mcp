"""Compatibility import for the canonical GUI request."""

try:
    from ...dispatch.gui_request import GuiRequest
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.gui_request import GuiRequest

__all__ = ["GuiRequest"]
