"""Validate the migration section of a sidecar payload."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..sidecar_types.sidecar_malformed_error import SidecarMalformedError
from .schema_expect import expect_keys, expect_string, expect_uuid


def validate_migration(
    migration: Any,
    *,
    document: Mapping[str, Any],
) -> None:
    migration = expect_keys(
        migration,
        name="migration",
        required={"migration_id", "source", "destination", "role"},
    )
    expect_uuid(migration["migration_id"], "migration.migration_id")
    source = expect_keys(
        migration["source"],
        name="migration.source",
        required={"canonical_path", "comparison_key"},
    )
    destination = expect_keys(
        migration["destination"],
        name="migration.destination",
        required={"canonical_path", "comparison_key"},
    )
    for field in ("canonical_path", "comparison_key"):
        if source[field] is not None:
            expect_string(source[field], f"migration.source.{field}")
        expect_string(
            destination[field], f"migration.destination.{field}"
        )
    if bool(source["canonical_path"]) != bool(source["comparison_key"]):
        raise SidecarMalformedError(
            "migration source canonical_path and comparison_key must "
            "both be set or both be null"
        )
    if not destination["canonical_path"] or not destination["comparison_key"]:
        raise SidecarMalformedError(
            "migration destination path identity must not be empty"
        )
    if (
        source["comparison_key"] is not None
        and source["comparison_key"] == destination["comparison_key"]
    ):
        raise SidecarMalformedError(
            "migration source and destination must identify different paths"
        )
    role = expect_string(migration["role"], "migration.role", max_length=16)
    if role not in {"source", "destination"}:
        raise SidecarMalformedError("migration.role is invalid")
    endpoint = source if role == "source" else destination
    if role == "source" and endpoint["canonical_path"] is None:
        raise SidecarMalformedError(
            "a source migration record requires a saved source path"
        )
    if (
        document["canonical_path"] != endpoint["canonical_path"]
        or document["comparison_key"] != endpoint["comparison_key"]
    ):
        raise SidecarMalformedError(
            "migration role identity does not match the sidecar document"
        )
