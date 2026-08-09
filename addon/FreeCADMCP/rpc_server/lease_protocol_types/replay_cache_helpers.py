"""Compatibility imports for canonical replay-cache helpers."""

try:
    from ..._shared.protocol.replay_cache_helpers import (
        completion_tombstone,
        is_completion_tombstone,
        scrub_exact_secrets,
    )
except ImportError:
    from _shared.protocol.replay_cache_helpers import (
        completion_tombstone,
        is_completion_tombstone,
        scrub_exact_secrets,
    )

__all__ = ["completion_tombstone", "is_completion_tombstone", "scrub_exact_secrets"]
