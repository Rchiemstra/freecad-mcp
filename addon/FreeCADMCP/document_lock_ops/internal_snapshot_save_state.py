from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class _InternalSnapshotSaveState:
    """Exact synchronous marker for one trusted worker ``saveCopy``."""

    request_id: str = ""
    document: Any = field(default=None, repr=False)
    target_path: str = ""
    depth: int = 0
    violation: str = ""
