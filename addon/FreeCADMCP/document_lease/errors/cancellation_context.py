"""Internal cancellation bookkeeping for in-flight lease mutations."""

from __future__ import annotations

from dataclasses import dataclass

from ..types.lease_state import LeaseState


@dataclass(frozen=True)
class _CancellationContext:
    request_id: str
    previous_state: LeaseState
    previous_operation: str
    mutation_may_have_begun: bool = False


_CancellationContext.__module__ = "document_lease.service"
