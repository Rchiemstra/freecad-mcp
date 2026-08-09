"""Validate the lease section of a sidecar payload."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..model import LeaseState
from ..sidecar_types.sidecar_malformed_error import SidecarMalformedError
from .schema_expect import expect_int, expect_keys, expect_string, expect_timestamp


def validate_lease(lease: Any) -> Mapping[str, Any]:
    lease = expect_keys(
        lease,
        name="lease",
        required={
            "state",
            "state_revision",
            "acquired_at",
            "last_heartbeat_at",
            "heartbeat_sequence",
            "current_operation",
            "task_summary",
        },
    )
    try:
        LeaseState(lease["state"])
    except (ValueError, TypeError) as exc:
        raise SidecarMalformedError("lease.state is invalid") from exc
    expect_int(lease["state_revision"], "lease.state_revision", minimum=1)
    expect_int(lease["heartbeat_sequence"], "lease.heartbeat_sequence")
    expect_timestamp(lease["acquired_at"], "lease.acquired_at")
    expect_timestamp(lease["last_heartbeat_at"], "lease.last_heartbeat_at")
    expect_string(lease["current_operation"], "lease.current_operation", max_length=512)
    expect_string(lease["task_summary"], "lease.task_summary", max_length=1024)
    return lease
