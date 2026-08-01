"""Document health validation profile levels."""

from __future__ import annotations

from enum import StrEnum


class ValidationProfile(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    DEFAULT = "default"
    FULL = "full"
