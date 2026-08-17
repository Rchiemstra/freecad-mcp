"""Shared Part 3 admission helpers for authenticated mutating RPCs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

try:
    from .identity import bootstrap_identity_selector
    from .operation_terminal_store import OperationReplayCheck, check_operation_terminal
except ImportError:  # pragma: no cover - flat addon import path
    from addon.FreeCADMCP.part3_collaboration.identity import bootstrap_identity_selector
    from addon.FreeCADMCP.part3_collaboration.operation_terminal_store import (
        OperationReplayCheck,
        check_operation_terminal,
    )


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": False,
        "ok": False,
        "error_code": code,
        "error": message,
    }
    payload.update(extra)
    return payload


def actor_from_session(self) -> tuple[str | None, dict[str, Any] | None]:
    identity = self._execution_collaborators.request_identity_provider().get_request_identity()
    actor_id = identity.get("authenticated_session_id")
    if not actor_id:
        return None, _error(
            "LEASE_PROTOCOL_REQUIRED",
            "This operation requires a handshake_v2 session and an immutable authenticated request envelope",
        )
    return str(actor_id), None


def early_operation_replay(
    self,
    operation_id: str,
    canonical_payload: Mapping[str, Any],
    document: Any,
) -> tuple[OperationReplayCheck, dict[str, Any] | None]:
    actor_id, auth_failure = actor_from_session(self)
    if auth_failure is not None:
        return OperationReplayCheck("auth_failure"), auth_failure
    if not operation_id:
        return OperationReplayCheck("auth_failure"), _error(
            "OPERATION_ID_REQUIRED",
            "operation_id is required",
        )

    selector = bootstrap_identity_selector(document)
    replay = check_operation_terminal(
        actor_id,
        str(operation_id),
        canonical_payload,
        live_document_instance_id=int(selector.document_instance_id),
        live_lifecycle_epoch=int(selector.lifecycle_epoch),
    )
    return replay, None


def early_operation_replay_across_documents(
    self,
    operation_id: str,
    canonical_payload: Mapping[str, Any],
    documents: list[Any],
) -> tuple[OperationReplayCheck, dict[str, Any] | None]:
    """Probe live documents for a stored terminal before session-specific admission."""

    actor_id, auth_failure = actor_from_session(self)
    if auth_failure is not None:
        return OperationReplayCheck("auth_failure"), auth_failure
    if not operation_id:
        return OperationReplayCheck("auth_failure"), _error(
            "OPERATION_ID_REQUIRED",
            "operation_id is required",
        )

    stale: OperationReplayCheck | None = None
    for document in documents:
        try:
            selector = bootstrap_identity_selector(document)
        except TypeError:
            continue
        replay = check_operation_terminal(
            actor_id,
            str(operation_id),
            canonical_payload,
            live_document_instance_id=int(selector.document_instance_id),
            live_lifecycle_epoch=int(selector.lifecycle_epoch),
        )
        if replay.state in ("replay", "conflict"):
            return replay, None
        if replay.state == "stale_lifecycle":
            stale = replay
    if stale is not None:
        return stale, None
    return OperationReplayCheck("new"), None


def replay_or_protocol_error(replay: OperationReplayCheck) -> dict[str, Any] | None:
    if replay.state == "replay" and replay.terminal_result is not None:
        return replay.terminal_result
    if replay.state == "conflict":
        return _error(
            "OPERATION_PAYLOAD_CONFLICT",
            "operation_id was reused with a different canonical payload",
        )
    if replay.state == "stale_lifecycle":
        return _error(
            "DOCUMENT_LIFECYCLE_REJECTED",
            "stored operation result targets a stale document instance",
        )
    return None


__all__ = [
    "actor_from_session",
    "early_operation_replay",
    "early_operation_replay_across_documents",
    "replay_or_protocol_error",
]
