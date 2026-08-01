"""Stale recovery result DTO."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class StaleRecoveryResult:
    """Token-free outcome for one automatic stale-recovery attempt."""

    document_session_uuid: str
    trigger: str
    outcome: str
    reason_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        from .stale_recovery_helpers import stale_recovery_result_to_dict

        return stale_recovery_result_to_dict(self)
