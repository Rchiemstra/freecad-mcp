"""_RecoveryAttemptState — extracted from lease_manager."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RecoveryAttemptState:
    attempt_count: int = 0
    last_attempt_monotonic: float = 0.0
    next_allowed_monotonic: float = 0.0
    terminal: bool = False
    terminal_reason_code: str = ""
