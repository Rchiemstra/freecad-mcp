"""Base error raised to the XML-RPC handler by GUI dispatch."""

from __future__ import annotations

from typing import Any


class GuiDispatchError(RuntimeError):
    """Base error raised to the XML-RPC handler by GUI dispatch."""

    error_code = "GUI_DISPATCH_FAILED"

    def __init__(
        self,
        message: str,
        *,
        request_id: str | None = None,
        timeout_stage: str | None = None,
        execution_started: bool = False,
        mutation_started: bool = False,
        completion_uncertain: bool = False,
    ) -> None:
        self.request_id = request_id
        self.timeout_stage = timeout_stage
        self.execution_started = bool(execution_started)
        self.mutation_started = bool(mutation_started)
        self.completion_uncertain = bool(completion_uncertain)
        super().__init__(message)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "timeout_stage": self.timeout_stage,
            "request_id": self.request_id,
            "execution_started": self.execution_started,
            "mutation_started": self.mutation_started,
            "completion_uncertain": self.completion_uncertain,
        }
