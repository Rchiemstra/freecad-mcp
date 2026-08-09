from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LeaseErrorInfo:
    code: str
    message: str
    at: str
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "at": self.at,
            "request_id": self.request_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> LeaseErrorInfo | None:
        if data is None:
            return None
        return cls(
            code=str(data["code"]),
            message=str(data["message"]),
            at=str(data["at"]),
            request_id=data.get("request_id"),
        )

LeaseErrorInfo.__module__ = "document_lease.model"
