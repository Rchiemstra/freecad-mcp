"""Risk DTO for expensive OCCT calls inside Python control flow."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GuiGeometryLoopRisk:
    expensive_calls: int
    worker_only_calls: int
    loops: int
    reason: str
