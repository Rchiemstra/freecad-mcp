"""Compatibility import for the canonical request replay cache."""

try:
    from ..._shared.protocol.request_replay_cache import RequestReplayCache
except ImportError:
    from _shared.protocol.request_replay_cache import RequestReplayCache

__all__ = ["RequestReplayCache"]
