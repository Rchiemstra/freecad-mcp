"""Validate the document section of a sidecar payload."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..sidecar_types.sidecar_malformed_error import SidecarMalformedError
from .schema_expect import (
    expect_keys,
    expect_string,
    expect_uuid,
    validate_file_identity,
)


def validate_document(document: Any) -> Mapping[str, Any]:
    document = expect_keys(
        document,
        name="document",
        required={
            "session_uuid",
            "name",
            "canonical_path",
            "comparison_key",
            "file_identity",
        },
    )
    expect_uuid(document["session_uuid"], "document.session_uuid")
    expect_string(document["name"], "document.name", max_length=512)
    for field in ("canonical_path", "comparison_key"):
        if document[field] is not None:
            expect_string(document[field], f"document.{field}")
    if bool(document["canonical_path"]) != bool(document["comparison_key"]):
        raise SidecarMalformedError(
            "canonical_path and comparison_key must both be set or both be null"
        )
    validate_file_identity(document["file_identity"], "document.file_identity")
    return document
