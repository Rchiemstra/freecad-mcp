"""Compatibility import for the canonical replay check."""

try:
    from ..._shared.protocol.replay_check import ReplayCheck
except ImportError:
    from _shared.protocol.replay_check import ReplayCheck

__all__ = ["ReplayCheck"]
