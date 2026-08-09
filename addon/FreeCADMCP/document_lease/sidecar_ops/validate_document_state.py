"""Validate the document_state section of a sidecar payload."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..model import LeaseState
from ..sidecar_types.sidecar_malformed_error import SidecarMalformedError
from .schema_expect import (
    expect_bool,
    expect_int,
    expect_keys,
    expect_string,
    expect_timestamp,
    validate_file_identity,
)


def validate_document_state(state: Any) -> Mapping[str, Any]:
    state = expect_keys(
        state,
        name="document_state",
        required={
            "dirty",
            "user_intervened",
            "last_mutation_revision",
            "last_successful_save_at",
            "last_verified_save_revision",
            "baseline",
            "error",
            "validation_complete",
            "snapshot_id",
        },
    )
    expect_bool(state["dirty"], "document_state.dirty")
    expect_bool(state["user_intervened"], "document_state.user_intervened")
    expect_bool(state["validation_complete"], "document_state.validation_complete")
    expect_int(
        state["last_mutation_revision"], "document_state.last_mutation_revision"
    )
    expect_int(
        state["last_verified_save_revision"],
        "document_state.last_verified_save_revision",
    )
    for field in ("last_successful_save_at", "snapshot_id"):
        if state[field] is not None:
            expect_string(state[field], f"document_state.{field}", max_length=512)
    if state["last_successful_save_at"] is not None:
        expect_timestamp(
            state["last_successful_save_at"],
            "document_state.last_successful_save_at",
        )

    if state["baseline"] is not None:
        baseline = expect_keys(
            state["baseline"],
            name="document_state.baseline",
            required={"mtime_ns", "size", "sha256", "file_identity"},
        )
        expect_int(baseline["mtime_ns"], "baseline.mtime_ns")
        expect_int(baseline["size"], "baseline.size")
        sha = expect_string(baseline["sha256"], "baseline.sha256", max_length=64)
        if len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha):
            raise SidecarMalformedError("baseline.sha256 must be lowercase SHA-256")
        validate_file_identity(baseline["file_identity"], "baseline.file_identity")

    if state["error"] is not None:
        error_data = expect_keys(
            state["error"],
            name="document_state.error",
            required={"code", "message", "at", "request_id"},
        )
        for field, maximum in (("code", 128), ("message", 2048), ("at", 64)):
            expect_string(error_data[field], f"error.{field}", max_length=maximum)
        expect_timestamp(error_data["at"], "error.at")
        if error_data["request_id"] is not None:
            expect_string(error_data["request_id"], "error.request_id", max_length=64)
    return state


def validate_cross_field_rules(
    *,
    record_revision: int,
    lease: Mapping[str, Any],
    state: Mapping[str, Any],
) -> None:
    if record_revision < lease["state_revision"]:
        raise SidecarMalformedError("record_revision cannot predate state_revision")
    if state["last_verified_save_revision"] > state["last_mutation_revision"]:
        raise SidecarMalformedError(
            "last_verified_save_revision cannot exceed last_mutation_revision"
        )
    if lease["state"] == LeaseState.USER_INTERVENED.value and not state[
        "user_intervened"
    ]:
        raise SidecarMalformedError(
            "USER_INTERVENED state requires user_intervened=true"
        )
    if lease["state"] == LeaseState.LOCKED_ERROR.value and state["error"] is None:
        raise SidecarMalformedError("LOCKED_ERROR state requires structured error metadata")
