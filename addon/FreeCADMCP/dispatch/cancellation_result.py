"""Public cancellation status for one authenticated request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .inflight_snapshot import InflightSnapshot


@dataclass(frozen=True)
class CancellationResult:
    status: str
    request: InflightSnapshot | None

    def to_public_dict(self) -> dict[str, Any]:
        result = {"status": self.status}
        if self.request is not None:
            result["request"] = self.request.to_public_dict()
        return result
