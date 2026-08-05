"""Extracted ``_ReplayEntry`` for ARCH002 (workstream 1G)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class _ReplayEntry:
    fingerprint: str
    expires_at: float
    pin_to_owner_leases: bool = False
    process_pinned: bool = False
    state: str = "in_progress"
    response: Any = None
    response_compacted: bool = False
    late_completion_journaled: bool = False
