"""Compatibility import for the canonical session context."""

try:
    from ..._shared.protocol.session_context import SessionContext
except ImportError:
    from _shared.protocol.session_context import SessionContext

__all__ = ["SessionContext"]
