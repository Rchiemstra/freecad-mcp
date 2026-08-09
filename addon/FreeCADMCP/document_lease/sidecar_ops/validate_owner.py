"""Validate the owner section of a sidecar payload."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .schema_expect import expect_int, expect_keys, expect_string, expect_timestamp, expect_uuid


def validate_owner(owner: Any) -> Mapping[str, Any]:
    owner_fields = {
        "addon_profile_id",
        "addon_runtime_id",
        "freecad_pid",
        "freecad_process_started_at",
        "boot_id",
        "mcp_instance_id",
        "mcp_pid",
        "mcp_process_started_at",
        "hostname",
        "client",
        "agent_id",
    }
    owner = expect_keys(
        owner,
        name="owner",
        required=owner_fields,
        optional={"mcp_hostname"},
    )
    expect_uuid(owner["addon_profile_id"], "owner.addon_profile_id")
    expect_uuid(owner["addon_runtime_id"], "owner.addon_runtime_id")
    expect_uuid(owner["mcp_instance_id"], "owner.mcp_instance_id")
    expect_int(owner["freecad_pid"], "owner.freecad_pid", minimum=1)
    expect_int(owner["mcp_pid"], "owner.mcp_pid", minimum=1)
    for field in owner_fields - {"freecad_pid", "mcp_pid"}:
        if field not in {"addon_profile_id", "addon_runtime_id", "mcp_instance_id"}:
            expect_string(owner[field], f"owner.{field}", max_length=512)
    expect_timestamp(
        owner["freecad_process_started_at"], "owner.freecad_process_started_at"
    )
    expect_timestamp(
        owner["mcp_process_started_at"], "owner.mcp_process_started_at"
    )
    if "mcp_hostname" in owner:
        expect_string(owner["mcp_hostname"], "owner.mcp_hostname", max_length=512)
    return owner
