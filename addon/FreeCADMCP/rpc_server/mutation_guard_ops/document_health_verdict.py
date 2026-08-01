"""Document health verdict after mutation postflight."""

from __future__ import annotations

from enum import StrEnum


class DocumentHealthVerdict(StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    DEGRADED = "degraded"
    INVALID = "invalid"
    UNKNOWN = "unknown"
