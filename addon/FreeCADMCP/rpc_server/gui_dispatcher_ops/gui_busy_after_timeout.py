"""Compatibility import for the canonical GUI busy error."""

try:
    from ...dispatch.gui_errors import GuiBusyAfterTimeout
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.gui_errors import GuiBusyAfterTimeout

__all__ = ["GuiBusyAfterTimeout"]
