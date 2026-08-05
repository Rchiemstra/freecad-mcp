"""Native document lifecycle dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LifecycleCollaborators:
    """Minimal dependency graph for native FreeCAD lifecycle adapters."""

    freecad: Any

    def __post_init__(self) -> None:
        if self.freecad is None:
            raise ValueError("freecad collaborator is required")


__all__ = ["LifecycleCollaborators"]
