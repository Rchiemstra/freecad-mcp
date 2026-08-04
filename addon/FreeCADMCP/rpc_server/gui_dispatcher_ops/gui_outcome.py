"""Compatibility import for the canonical GUI outcome."""

try:
    from ...dispatch.gui_outcome import GuiOutcome
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.gui_outcome import GuiOutcome

__all__ = ["GuiOutcome"]
