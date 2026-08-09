"""Compatibility import for the canonical replay entry."""

try:
    from ..._shared.protocol._replay_entry import _ReplayEntry
except ImportError:
    from _shared.protocol._replay_entry import _ReplayEntry

__all__ = ["_ReplayEntry"]
