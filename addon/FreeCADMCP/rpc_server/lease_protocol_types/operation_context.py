"""Extracted ``OperationContext`` for ARCH002 (workstream 1G)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .lease_protocol_error import LeaseProtocolError
from .validation import _require_exact_keys, _require_string, _require_uuid


@dataclass(frozen=True)
class OperationContext:
    name: str
    task_id: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> OperationContext:
        if not isinstance(payload, Mapping):
            raise LeaseProtocolError(
                "MALFORMED_ENVELOPE", "Operation metadata must be an object"
            )
        _require_exact_keys(
            payload,
            required={"name"},
            optional={"task_id"},
            context="operation metadata",
        )
        task_id = payload.get("task_id")
        return cls(
            name=_require_string(payload["name"], "operation.name", maximum=256),
            task_id=None if task_id is None else _require_uuid(task_id, "operation.task_id"),
        )


OperationContext.__module__ = "rpc_server.lease_protocol"
