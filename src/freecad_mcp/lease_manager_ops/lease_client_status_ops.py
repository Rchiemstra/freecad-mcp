"""LeaseClientManager method implementations."""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from typing import Any

from .lease_manager_closed_error import LeaseManagerClosedError
from .lease_manager_disconnected_error import LeaseManagerDisconnectedError


def redacted_status(manager) -> dict[str, Any]:
        """Return a stable, fully non-secret diagnostic snapshot."""

        with manager._lock:
            credentials = []
            for session_uuid in sorted(manager._credentials):
                item = manager._credentials[session_uuid].redacted()
                item["canonical_paths"] = sorted(
                    manager._session_aliases.get(session_uuid, ())
                )
                credentials.append(item)
            return {
                "connected": manager._connected,
                "closed": manager._closed,
                "disconnect_reason": manager._disconnect_reason,
                "disconnected_at": manager._disconnected_at,
                "credentials": credentials,
                "revocations": [
                    {
                        "document_session_uuid": item.document_session_uuid,
                        "lease_id": item.lease_id,
                        "generation": item.generation,
                        "reason": item.reason,
                        "user_intervened": item.user_intervened,
                        "revoked_at": item.revoked_at,
                    }
                    for _, item in sorted(manager._revocations.items())
                ],
            }


def _require_connected_locked(manager) -> None:
        manager._require_open_locked()
        if not manager._connected:
            raise LeaseManagerDisconnectedError(
                manager._disconnect_reason or "lease manager is disconnected"
            )
        if not manager._session_token:
            raise LeaseManagerDisconnectedError(
                "no authenticated RPC session is installed"
            )


def _require_open_locked(manager) -> None:
        if manager._closed:
            raise LeaseManagerClosedError("lease manager is closed")


def _build_heartbeat_payload_locked(
        manager,
        current_operations: Mapping[str, str] | None,
    ) -> dict[str, Any]:
        operations = current_operations or {}
        leases = []
        for session_uuid in sorted(manager._credentials):
            credential = manager._credentials[session_uuid]
            item = credential.to_wire()
            operation = operations.get(session_uuid)
            if operation:
                item["current_operation"] = str(operation)
            leases.append(item)
        return {
            "leases": leases,
            # Retain the established decimal-text shape for compatibility.
            "client_monotonic_ns": str(time.monotonic_ns()),
        }


def redact_text(
        manager,
        value: Any,
        *,
        additional_secrets: Iterable[str] = (),
    ) -> str:
        """Scrub every currently held credential from diagnostic text."""

        with manager._lock:
            secrets = (*manager._secret_snapshot_locked(), *tuple(additional_secrets))
            return manager._redact_text_with_secrets(str(value), secrets)


def redact_value(
        manager,
        value: Any,
        *,
        additional_secrets: Iterable[str] = (),
    ) -> Any:
        """Return a recursively scrubbed copy suitable for logs/public errors."""

        with manager._lock:
            secrets = (*manager._secret_snapshot_locked(), *tuple(additional_secrets))

        def scrub(item: Any) -> Any:
            if isinstance(item, str):
                return manager._redact_text_with_secrets(item, secrets)
            if isinstance(item, Mapping):
                return {
                    manager._redact_text_with_secrets(str(key), secrets): scrub(child)
                    for key, child in item.items()
                }
            if isinstance(item, tuple):
                return tuple(scrub(child) for child in item)
            if isinstance(item, list):
                return [scrub(child) for child in item]
            return item

        return scrub(value)


def _secret_snapshot_locked(manager) -> tuple[str, ...]:
        secrets = [credential.token for credential in manager._credentials.values()]
        if manager._session_token:
            secrets.append(manager._session_token)
        return tuple(secret for secret in secrets if secret)


def _redact_text_with_secrets(value: Any, secrets: Iterable[str]) -> str:
        safe = str(value)
        for secret in secrets:
            if secret:
                safe = safe.replace(secret, "[REDACTED]")
        return safe


def _redact_text_locked(manager, value: str) -> str:
        return manager._redact_text_with_secrets(value, manager._secret_snapshot_locked())
