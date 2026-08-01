"""Outcome container for GUI-thread callables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GuiOutcome:
    ok: bool
    value: Any = None
    error: str | None = None
