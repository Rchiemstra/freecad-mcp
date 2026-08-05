"""Outcome value returned across the GUI dispatch boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GuiOutcome:
    ok: bool
    value: Any = None
    error: str | None = None
    late: bool = False
