"""Base structured save failure for RPC error responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SaveServiceError(RuntimeError):
    """Structured save failure suitable for an RPC error response."""

    __module__ = "rpc_server.save_service"

    code = "SAVE_SERVICE_ERROR"

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        path: str | None = None,
        mutation_may_have_occurred: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.stage = stage
        self.path = path
        self.mutation_may_have_occurred = bool(mutation_may_have_occurred)
        self.details = dict(details or {})
        super().__init__(message)

    def to_dict(self, *, request_id: str | None = None) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": str(self),
            "stage": self.stage,
            "mutation_may_have_occurred": self.mutation_may_have_occurred,
            "details": dict(self.details),
        }
        if self.path is not None:
            error["path"] = self.path
        if request_id:
            error["request_id"] = request_id
        return error
