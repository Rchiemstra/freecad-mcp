"""In-flight LOCKED_ERROR handoff continuation state."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HandoffContinuation:
    mcp_runtime_id: str
    request_id: str
    state: str = "pending_authorization"
    stage: str = "handoff_authorize"
    error_code: str | None = None
    error: str | None = None
    cancel_requested: threading.Event = field(default_factory=threading.Event)
    created_monotonic: float = field(default_factory=time.monotonic)
    updated_monotonic: float = field(default_factory=time.monotonic)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "stage": self.stage,
            # Retained for wire compatibility. Handoff is now auto-authorized.
            "confirmation_pending": False,
            "handoff_pending": self.state
            in {
                "pending_authorization",
                "authorizing",
                "hashing",
                "claiming",
                "claim_committed",
                "claiming_uncertain",
            },
            "cancellation_requested": self.cancel_requested.is_set(),
            "error_code": self.error_code,
            "error": self.error,
        }
