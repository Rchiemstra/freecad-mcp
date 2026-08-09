"""UTC timestamp helpers for process and boot evidence."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_timestamp(value: float) -> str:
    return (
        datetime.fromtimestamp(value, UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
