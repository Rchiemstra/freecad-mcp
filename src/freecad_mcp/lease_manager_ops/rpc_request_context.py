"""RpcRequestContext — extracted from lease_manager."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .lease_credential import LeaseCredential


@dataclass(frozen=True, slots=True)
class RpcRequestContext:
    """Immutable authentication context for one v2 RPC invocation."""

    request_id: str
    session_token: str = field(repr=False)
    lease_credentials: tuple[LeaseCredential, ...] = ()
    operation_name: str = ""
    task_id: str = ""
    protocol_version: int = 2

    def __post_init__(self) -> None:
        if self.protocol_version != 2:
            raise ValueError("only RPC protocol version 2 is supported")
        try:
            parsed_request_id = uuid.UUID(str(self.request_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("request_id must be a UUID") from exc
        if parsed_request_id.int == 0:
            raise ValueError("request_id must not be the nil UUID")
        object.__setattr__(self, "request_id", str(parsed_request_id))
        if not self.session_token:
            raise ValueError("session_token must not be empty")
        if not isinstance(self.lease_credentials, tuple):
            object.__setattr__(self, "lease_credentials", tuple(self.lease_credentials))
        sessions = [item.document_session_uuid for item in self.lease_credentials]
        if len(sessions) != len(set(sessions)):
            raise ValueError("request context contains duplicate document credentials")
        if self.task_id:
            try:
                parsed_task_id = uuid.UUID(str(self.task_id))
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValueError("task_id must be a UUID") from exc
            if parsed_task_id.int == 0:
                raise ValueError("task_id must not be the nil UUID")
            object.__setattr__(self, "task_id", str(parsed_task_id))

    def to_envelope(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a fresh XML-RPC-serializable envelope for this request."""

        if not method:
            raise ValueError("method must not be empty")
        envelope = {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "session_token": self.session_token,
            "method": method,
            "params": copy.deepcopy(dict(params or {})),
            "lease_credentials": [item.to_wire() for item in self.lease_credentials],
        }
        if self.operation_name:
            operation = {"name": self.operation_name}
            if self.task_id:
                operation["task_id"] = self.task_id
            envelope["operation"] = operation
        return envelope
