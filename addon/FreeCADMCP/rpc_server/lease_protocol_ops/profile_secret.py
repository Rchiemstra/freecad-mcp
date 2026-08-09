"""Compatibility imports for canonical profile-secret operations."""

from __future__ import annotations

try:
    from ..._shared.protocol.profile_secret import (
        create_profile_secret,
        load_profile_secret,
    )
except ImportError:
    from _shared.protocol.profile_secret import (
        create_profile_secret,
        load_profile_secret,
    )

__all__ = ["create_profile_secret", "load_profile_secret"]
