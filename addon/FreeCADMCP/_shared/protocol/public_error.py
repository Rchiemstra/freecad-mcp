"""Bounded public error payloads for authenticated RPC v2."""

from __future__ import annotations

import uuid
from typing import Any

from .protocol_error import ProtocolError
from .validation import _is_uuid


def public_error(
    error: BaseException,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Return a bounded error payload without exception internals or secrets."""

    if isinstance(error, ProtocolError):
        return error.to_public_dict(request_id=request_id)
    result: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": "INTERNAL_PROTOCOL_ERROR",
            "message": "The authenticated RPC request could not be processed",
        },
    }
    if request_id is not None and _is_uuid(request_id):
        result["request_id"] = str(uuid.UUID(request_id))
    return result
