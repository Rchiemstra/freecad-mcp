"""Opaque, non-authorizing handle for an already-created native session."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True, repr=False)
class NativeSessionHandle:
    """Wrap a validated native session identifier without assigning authority.

    This is a transport boundary value only.  It records no owner, token,
    generation, heartbeat, or authorization state.
    """

    opaque_id: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.opaque_id, str):
            raise TypeError("native session ID must be a string")
        if not self.opaque_id.strip():
            raise ValueError("native session ID must not be empty")

    def to_native_argument(self) -> str:
        """Return the opaque identifier for the native API boundary."""

        return self.opaque_id

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"
