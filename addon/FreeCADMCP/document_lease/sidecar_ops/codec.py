"""Parse and serialize guarded sidecar records."""

from __future__ import annotations

import json

from ..model import LeaseRecord
from ..sidecar_types.sidecar_malformed_error import SidecarMalformedError
from ..sidecar_types.sidecar_too_large_error import SidecarTooLargeError
from .constants import MAX_SIDECAR_BYTES
from .validate_payload import validate_sidecar_payload


def parse_sidecar_bytes(data: bytes, *, max_bytes: int = MAX_SIDECAR_BYTES) -> LeaseRecord:
    if len(data) > max_bytes:
        raise SidecarTooLargeError(
            f"sidecar exceeds the {max_bytes}-byte safety limit"
        )
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SidecarMalformedError(f"sidecar is not valid UTF-8 JSON: {exc}") from exc
    validated = validate_sidecar_payload(value)
    try:
        return LeaseRecord.from_sidecar_dict(validated)
    except (KeyError, TypeError, ValueError) as exc:
        raise SidecarMalformedError(f"sidecar record is invalid: {exc}") from exc


def serialize_record(
    record: LeaseRecord,
    *,
    max_bytes: int,
    persist_task_summary: bool = False,
) -> bytes:
    encoded = json.dumps(
        record.to_sidecar_dict(include_task_summary=persist_task_summary),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > max_bytes:
        raise SidecarTooLargeError(
            f"serialized sidecar exceeds the {max_bytes}-byte safety limit"
        )
    # Validate our own output so invalid in-memory records cannot reach disk.
    parse_sidecar_bytes(encoded, max_bytes=max_bytes)
    return encoded
