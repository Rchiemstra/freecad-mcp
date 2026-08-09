"""Private vault entry for one acquisition credential."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClaimEntry:
    mcp_runtime_id: str
    request_id: str
    method: str
    credential: dict[str, Any] = field(repr=False)
    result: dict[str, Any] = field(repr=False)
    created_monotonic: float
    acknowledged: bool = False
