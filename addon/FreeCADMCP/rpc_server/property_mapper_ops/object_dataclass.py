"""JSON-friendly document object descriptor."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Object:
    name: str
    type: str | None = None
    analysis: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
