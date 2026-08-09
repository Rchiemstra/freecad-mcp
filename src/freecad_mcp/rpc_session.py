"""Short-lived RPC authentication state for the MCP client process."""

from __future__ import annotations

import copy
import threading
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RpcAuthenticationContext:
    """Immutable authentication evidence for one protocol-v2 invocation."""

    request_id: str
    session_token: str = field(repr=False)
    operation_name: str = ""
    task_id: str = ""
    protocol_version: int = 2

    def __post_init__(self) -> None:
        if self.protocol_version != 2:
            raise ValueError("only RPC protocol version 2 is supported")
        object.__setattr__(self, "request_id", _validated_uuid(self.request_id, "request_id"))
        if not self.session_token:
            raise ValueError("session_token must not be empty")
        if self.task_id:
            object.__setattr__(self, "task_id", _validated_uuid(self.task_id, "task_id"))

    def to_envelope(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a fresh v2 envelope containing authentication, never authority."""

        if not method:
            raise ValueError("method must not be empty")
        envelope: dict[str, Any] = {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "session_token": self.session_token,
            "method": method,
            "params": copy.deepcopy(dict(params or {})),
            "lease_credentials": [],
        }
        if self.operation_name:
            operation = {"name": self.operation_name}
            if self.task_id:
                operation["task_id"] = self.task_id
            envelope["operation"] = operation
        return envelope


class RpcAuthenticationSession:
    """Thread-safe custody for one replaceable add-on authentication token."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._session_token = ""
        self._session_id = ""
        self._expires_at = ""

    def __repr__(self) -> str:
        with self._lock:
            connected = bool(self._session_token)
            session_id = self._session_id
        return (
            f"{type(self).__name__}(connected={connected!r}, "
            f"session_id={session_id!r})"
        )

    @property
    def connected(self) -> bool:
        with self._lock:
            return bool(self._session_token)

    @property
    def session_id(self) -> str:
        with self._lock:
            return self._session_id

    @property
    def expires_at(self) -> str:
        with self._lock:
            return self._expires_at

    def mark_connected(
        self,
        session_token: str,
        *,
        session_id: str = "",
        expires_at: str = "",
    ) -> None:
        if not session_token:
            raise ValueError("session_token must not be empty")
        with self._lock:
            self._session_token = str(session_token)
            self._session_id = str(session_id or "")
            self._expires_at = str(expires_at or "")

    def mark_disconnected(self, reason: str = "connection closed") -> None:
        del reason
        with self._lock:
            self._session_token = ""
            self._session_id = ""
            self._expires_at = ""

    def close(self, reason: str = "MCP process shutdown") -> None:
        self.mark_disconnected(reason)

    def build_request_context(
        self,
        *,
        operation_name: str = "",
        task_id: str = "",
        request_id: str | None = None,
    ) -> RpcAuthenticationContext:
        with self._lock:
            token = self._session_token
        if not token:
            raise RuntimeError("RPC authentication session is not connected")
        return RpcAuthenticationContext(
            request_id=request_id or str(uuid.uuid4()),
            session_token=token,
            operation_name=operation_name,
            task_id=task_id,
        )

    def redact_text(
        self,
        value: Any,
        *,
        additional_secrets: Iterable[str] = (),
    ) -> str:
        with self._lock:
            secrets = (self._session_token, *tuple(additional_secrets))
        safe = str(value)
        for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
            safe = safe.replace(str(secret), "[REDACTED]")
        return safe

    def redact_value(
        self,
        value: Any,
        *,
        additional_secrets: Iterable[str] = (),
    ) -> Any:
        if isinstance(value, str):
            return self.redact_text(value, additional_secrets=additional_secrets)
        if isinstance(value, Mapping):
            return {
                self.redact_text(key, additional_secrets=additional_secrets): self.redact_value(
                    item,
                    additional_secrets=additional_secrets,
                )
                for key, item in value.items()
            }
        if isinstance(value, tuple):
            return tuple(
                self.redact_value(item, additional_secrets=additional_secrets)
                for item in value
            )
        if isinstance(value, list):
            return [
                self.redact_value(item, additional_secrets=additional_secrets)
                for item in value
            ]
        return value


def _validated_uuid(value: Any, field_name: str) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"{field_name} must be a UUID") from exc
    if parsed.int == 0:
        raise ValueError(f"{field_name} must not be the nil UUID")
    return str(parsed)


__all__ = ("RpcAuthenticationContext", "RpcAuthenticationSession")
