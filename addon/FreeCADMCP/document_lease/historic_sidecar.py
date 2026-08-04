"""Decode legacy sidecars into immutable, non-authoritative records."""

from __future__ import annotations

import json

from .model import HistoricLeaseRecord, decode_historic_lease_record
from .sidecar_ops.constants import MAX_SIDECAR_BYTES
from .sidecar_ops.validate_payload import validate_sidecar_payload
from .sidecar_types.sidecar_malformed_error import SidecarMalformedError
from .sidecar_types.sidecar_too_large_error import SidecarTooLargeError

_INVALID_JSON = object()
_INVALID_RECORD = object()


def _load_historic_json(data: bytes) -> object:
    """Parse without retaining untrusted bytes in a public exception chain."""

    try:
        return json.loads(data.decode("utf-8"))
    except (RecursionError, UnicodeDecodeError, json.JSONDecodeError):
        return _INVALID_JSON


def _decode_validated_historic_record(payload: object) -> HistoricLeaseRecord | object:
    """Validate without retaining untrusted schema errors as exception context."""

    try:
        validated = validate_sidecar_payload(payload)
        return decode_historic_lease_record(validated)
    except (KeyError, RecursionError, TypeError, ValueError, SidecarMalformedError):
        return _INVALID_RECORD


def decode_historic_sidecar_bytes(
    data: bytes, *, max_bytes: int = MAX_SIDECAR_BYTES
) -> HistoricLeaseRecord:
    """Validate historic sidecar bytes without restoring live lease authority.

    This decoder deliberately shares the established wire and schema bounds, but
    produces the historical, immutable projection rather than a ``LeaseRecord``.
    Its public errors never echo untrusted sidecar contents.
    """

    if len(data) > max_bytes:
        raise SidecarTooLargeError(
            f"sidecar exceeds the {max_bytes}-byte safety limit"
        )
    payload = _load_historic_json(data)
    if payload is _INVALID_JSON:
        raise SidecarMalformedError("historic sidecar is not valid UTF-8 JSON")
    record = _decode_validated_historic_record(payload)
    if record is _INVALID_RECORD:
        raise SidecarMalformedError("historic sidecar record is invalid")
    return record
