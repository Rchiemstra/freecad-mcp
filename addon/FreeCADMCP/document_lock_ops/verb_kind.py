from __future__ import annotations

from enum import StrEnum


class VerbKind(StrEnum):
    MUTATING = "MUTATING"
    READ_ONLY = "READ_ONLY"
    LIFECYCLE = "LIFECYCLE"
