"""Stable MCP result status values."""

from enum import StrEnum


class OutcomeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    CONDITION_FALSE = "condition_false"
    WARNING = "warning"
    DEGRADED = "degraded"
    REJECTED = "rejected"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
