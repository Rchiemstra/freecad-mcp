"""Raised when post-commit verification cannot confirm sidecar state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .sidecar_error import SidecarError

if TYPE_CHECKING:
    from ..model import LeaseRecord


class SidecarCommitUncertainError(SidecarError):
    """A filesystem mutation published but post-publication checks failed."""

    __module__ = "document_lease.sidecar"

    def __init__(
        self,
        message: str,
        *,
        persisted: LeaseRecord | None = None,
        absent: bool | None = None,
    ) -> None:
        self.persisted = persisted
        self.absent = absent
        super().__init__(message)
