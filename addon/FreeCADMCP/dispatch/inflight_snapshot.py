"""Immutable snapshot of one authenticated request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InflightSnapshot:
    session_id: str
    request_id: str
    method: str
    phase: str
    cancellation_requested: bool
    mutation_started: bool
    uncertain: bool
    handler_finished: bool
    active_gui_phases: int
    terminal: bool
    terminal_status: str | None
    cancel_requested_at: float | None
    cancellation_resolved: bool
    recovery_incident_id: str | None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "method": self.method,
            "phase": self.phase,
            "cancellation_requested": self.cancellation_requested,
            "mutation_started": self.mutation_started,
            "uncertain": self.uncertain,
            "handler_finished": self.handler_finished,
            "active_gui_phases": self.active_gui_phases,
            "terminal": self.terminal,
            "terminal_status": self.terminal_status,
            "cancellation_resolved": self.cancellation_resolved,
            "recovery_incident_id": self.recovery_incident_id,
        }
