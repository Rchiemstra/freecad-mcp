from __future__ import annotations

from .lease_model_error import LeaseModelError
from .lease_state import LeaseState


class InvalidTransitionError(LeaseModelError):
    __module__ = "document_lease.model"
    def __init__(self, current: LeaseState, target: LeaseState):
        self.current = current
        self.target = target
        super().__init__(f"invalid lease transition: {current.value} -> {target.value}")
