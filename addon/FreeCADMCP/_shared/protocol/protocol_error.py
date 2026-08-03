"""Stable, redacted errors for the canonical authenticated RPC protocol."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from .redaction import redact_sensitive


def _is_uuid(value: object) -> bool:
    try:
        return bool(value) and uuid.UUID(str(value)).int != 0
    except (ValueError, TypeError, AttributeError):
        return False


class ProtocolError(ValueError):
    """A protocol rejection with a stable, non-secret public representation."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = str(code)
        self.public_message = str(message)
        self.details = dict(details or {})
        super().__init__(f"{self.code}: {self.public_message}")

    def to_public_dict(self, *, request_id: str | None = None) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.public_message,
        }
        if self.details:
            error["details"] = redact_sensitive(self.details)
        result: dict[str, Any] = {"ok": False, "error": error}
        if request_id is not None and _is_uuid(request_id):
            result["request_id"] = str(uuid.UUID(request_id))
        return result
