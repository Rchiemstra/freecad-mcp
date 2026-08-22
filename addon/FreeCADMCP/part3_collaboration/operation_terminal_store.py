"""Server-enforced (MCP runtime, operation_id) terminal store for ADR §2.2."""

from __future__ import annotations

import copy
import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Any

try:
    from .._shared.protocol.validation import canonical_json_bytes
except ImportError:  # pragma: no cover - flat addon import path
    from addon.FreeCADMCP._shared.protocol.validation import canonical_json_bytes


@dataclass(frozen=True)
class OperationReplayCheck:
    state: str
    terminal_result: dict[str, Any] | None = None


@dataclass(frozen=True)
class _StoredTerminal:
    fingerprint: bytes
    document_instance_id: int
    lifecycle_epoch: int
    terminal_result: dict[str, Any]


_store: dict[tuple[str, str], _StoredTerminal] = {}
_lock = Lock()


def payload_fingerprint(payload: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(dict(payload))


def check_operation_terminal(
    runtime_owner_id: str,
    operation_id: str,
    canonical_payload: Mapping[str, Any],
    *,
    live_document_instance_id: int,
    live_lifecycle_epoch: int,
) -> OperationReplayCheck:
    """Look up a stored terminal result before mutating document state."""

    key = (str(runtime_owner_id), str(operation_id))
    fingerprint = payload_fingerprint(canonical_payload)
    with _lock:
        existing = _store.get(key)
        if existing is None:
            return OperationReplayCheck("new")
        if (
            existing.document_instance_id != int(live_document_instance_id)
            or existing.lifecycle_epoch != int(live_lifecycle_epoch)
        ):
            return OperationReplayCheck("stale_lifecycle")
        if not hmac.compare_digest(existing.fingerprint, fingerprint):
            return OperationReplayCheck("conflict")
        return OperationReplayCheck(
            "replay",
            copy.deepcopy(existing.terminal_result),
        )


def store_operation_terminal(
    runtime_owner_id: str,
    operation_id: str,
    canonical_payload: Mapping[str, Any],
    *,
    document_instance_id: int,
    lifecycle_epoch: int,
    terminal_result: Mapping[str, Any],
) -> None:
    key = (str(runtime_owner_id), str(operation_id))
    with _lock:
        _store[key] = _StoredTerminal(
            fingerprint=payload_fingerprint(canonical_payload),
            document_instance_id=int(document_instance_id),
            lifecycle_epoch=int(lifecycle_epoch),
            terminal_result=copy.deepcopy(dict(terminal_result)),
        )


def clear_operation_terminal_store() -> None:
    with _lock:
        _store.clear()


__all__ = [
    "OperationReplayCheck",
    "check_operation_terminal",
    "clear_operation_terminal_store",
    "payload_fingerprint",
    "store_operation_terminal",
]
