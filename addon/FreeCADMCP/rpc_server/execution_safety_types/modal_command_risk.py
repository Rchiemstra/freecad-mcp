"""Risk DTO for modal GUI entry points reached from unattended execute_code."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModalCommandRisk:
    kind: str
    trigger: str
    reason: str
