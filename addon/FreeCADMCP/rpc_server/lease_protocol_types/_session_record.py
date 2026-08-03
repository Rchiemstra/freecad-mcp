"""Compatibility import for the canonical session record."""

try:
    from ..._shared.protocol._session_record import _SessionRecord
except ImportError:
    from _shared.protocol._session_record import _SessionRecord

__all__ = ["_SessionRecord"]
