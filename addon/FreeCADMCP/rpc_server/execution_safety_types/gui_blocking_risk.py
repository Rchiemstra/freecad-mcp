"""Risk DTO for GUI-thread boolean blocking on transformed shapes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GuiBlockingRisk:
    boolean_calls: int
    transform_calls: int
    reason: str
