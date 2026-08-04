"""Raised at a cooperative phase boundary after cancellation was requested."""

from __future__ import annotations

from .inflight_snapshot import InflightSnapshot


class RequestCancellationError(RuntimeError):
    """Raised at a cooperative phase boundary after cancellation was requested."""

    code = "REQUEST_CANCELLED"

    def __init__(self, snapshot: InflightSnapshot) -> None:
        self.snapshot = snapshot
        suffix = (
            " after document mutation may have begun"
            if snapshot.mutation_started or snapshot.uncertain
            else " before document mutation began"
        )
        super().__init__(f"authenticated request was cancelled{suffix}")
