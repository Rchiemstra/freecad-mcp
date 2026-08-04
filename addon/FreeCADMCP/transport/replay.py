"""Transport-facing identity for the canonical request replay journal."""

try:
    from .._shared.protocol.request_replay_cache import RequestReplayCache
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from _shared.protocol.request_replay_cache import RequestReplayCache

__all__ = ["RequestReplayCache"]
