"""Validate every schema-v2 field before model construction."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..model import RECORD_KIND, SCHEMA_VERSION, TOKEN_FINGERPRINT_RE
from ..sidecar_types.sidecar_malformed_error import SidecarMalformedError
from .schema_expect import expect_int, expect_keys, expect_string, expect_uuid
from .validate_document import validate_document
from .validate_document_state import validate_cross_field_rules, validate_document_state
from .validate_lease import validate_lease
from .validate_migration import validate_migration
from .validate_owner import validate_owner


def validate_sidecar_payload(value: Any) -> Mapping[str, Any]:
    data = expect_keys(
        value,
        name="sidecar",
        required={
            "schema_version",
            "record_kind",
            "record_revision",
            "lease_id",
            "generation",
            "token_fingerprint",
            "document",
            "owner",
            "lease",
            "document_state",
        },
        optional={"migration"},
    )
    if data["schema_version"] != SCHEMA_VERSION:
        raise SidecarMalformedError(
            f"unsupported sidecar schema version: {data['schema_version']!r}"
        )
    if data["record_kind"] != RECORD_KIND:
        raise SidecarMalformedError("unrecognized sidecar record_kind")
    expect_int(data["record_revision"], "record_revision", minimum=1)
    expect_uuid(data["lease_id"], "lease_id")
    expect_int(data["generation"], "generation", minimum=1)
    fingerprint = expect_string(
        data["token_fingerprint"], "token_fingerprint", max_length=80
    )
    if not TOKEN_FINGERPRINT_RE.fullmatch(fingerprint):
        raise SidecarMalformedError("token_fingerprint must contain a SHA-256 digest")

    document = validate_document(data["document"])

    migration = data.get("migration")
    if migration is not None:
        validate_migration(migration, document=document)

    validate_owner(data["owner"])
    lease = validate_lease(data["lease"])
    state = validate_document_state(data["document_state"])
    validate_cross_field_rules(
        record_revision=data["record_revision"],
        lease=lease,
        state=state,
    )
    return data
