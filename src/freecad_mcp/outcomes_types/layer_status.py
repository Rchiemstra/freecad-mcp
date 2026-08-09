"""Per-layer MCP result status values."""

from enum import StrEnum


class LayerStatus(StrEnum):
    SUCCEEDED = "succeeded"
    CONDITION_FALSE = "condition_false"
    WARNING = "warning"
    DEGRADED = "degraded"
    REJECTED = "rejected"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"
