"""Schema field expectation helpers for sidecar validation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from ..sidecar_types.sidecar_malformed_error import SidecarMalformedError


def expect_keys(
    value: Any,
    *,
    name: str,
    required: set[str],
    optional: set[str] = frozenset(),
) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SidecarMalformedError(f"{name} must be an object")
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise SidecarMalformedError(f"{name} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise SidecarMalformedError(
            f"{name} contains unknown fields: {', '.join(sorted(unknown))}"
        )
    return value


def expect_string(value: Any, name: str, *, max_length: int = 4096) -> str:
    if not isinstance(value, str) or len(value) > max_length:
        raise SidecarMalformedError(f"{name} must be a bounded string")
    return value


def expect_int(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SidecarMalformedError(f"{name} must be an integer >= {minimum}")
    return value


def expect_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise SidecarMalformedError(f"{name} must be a boolean")
    return value


def expect_uuid(value: Any, name: str) -> str:
    text = expect_string(value, name, max_length=64)
    try:
        UUID(text)
    except (ValueError, AttributeError) as exc:
        raise SidecarMalformedError(f"{name} must be a UUID") from exc
    return text


def expect_timestamp(value: Any, name: str) -> str:
    text = expect_string(value, name, max_length=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SidecarMalformedError(f"{name} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise SidecarMalformedError(f"{name} must include a timezone")
    return text


def validate_file_identity(value: Any, name: str) -> None:
    if value is None:
        return
    data = expect_keys(
        value,
        name=name,
        required={"platform"},
        optional={"device", "inode", "volume_serial", "file_index"},
    )
    platform = expect_string(data["platform"], f"{name}.platform", max_length=16)
    expected = (
        {"volume_serial", "file_index"}
        if platform == "windows"
        else {"device", "inode"}
    )
    for key in expected:
        if key not in data or data[key] is None:
            raise SidecarMalformedError(f"{name}.{key} is required")
        expect_int(data[key], f"{name}.{key}")
