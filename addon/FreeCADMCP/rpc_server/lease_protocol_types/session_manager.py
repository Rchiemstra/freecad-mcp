"""Compatibility import for the canonical session manager."""

try:
    from ..._shared.protocol.session_manager import SessionManager
except ImportError:
    from _shared.protocol.session_manager import SessionManager

__all__ = ["SessionManager"]
