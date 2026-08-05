"""FreeCADConnection authenticated control-lane methods."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from ...rpc_session import RpcAuthenticationContext
from ..rpc_invocation_error import RpcInvocationError
from .connection_disconnect_helpers import (
    close_transport_lane,
    mark_connection_disconnected,
)


def heartbeat_document_locks_batch(
    conn,
    payload: Mapping[str, Any],
    context: RpcAuthenticationContext,
) -> dict[str, Any]:
    del conn, payload, context
    return _legacy_authority_removed()


def reconcile_document_lease(
    conn,
    document_session_uuid: str,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    del conn, document_session_uuid, request_id
    return _legacy_authority_removed()


def get_request_status(
    conn,
    target_request_id: str,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    target = _validated_request_id(target_request_id, "target_request_id")
    context = conn._build_v2_context(
        operation_name="Get request status",
        request_id=request_id,
        require_credentials=False,
    )
    if context is None:
        return _authentication_required("Request status")
    response = conn.invoke_v2(
        "get_request_status",
        {"request_id": target},
        context,
        control=True,
    )
    return conn._unwrap_v2_response(
        response,
        additional_secrets=(context.session_token,),
    )


def claim_acquisition_result(
    conn,
    target_request_id: str,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    del conn, target_request_id, request_id
    return _legacy_authority_removed()


def acknowledge_acquisition_claim(
    conn,
    target_request_id: str,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    del conn, target_request_id, request_id
    return _legacy_authority_removed()


def cancel_request(
    conn,
    target_request_id: str,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    target = _validated_request_id(target_request_id, "target_request_id")
    context = conn._build_v2_context(
        operation_name="Cancel request",
        request_id=request_id,
        require_credentials=False,
    )
    if context is None:
        return _authentication_required("Request cancellation")
    response = conn.invoke_v2(
        "cancel_request",
        {"target_request_id": target},
        context,
        control=True,
    )
    return conn._unwrap_v2_response(
        response,
        additional_secrets=(context.session_token,),
    )


def notify_cancel_request(
    conn,
    target_request_id: str,
    *,
    request_id: str | None = None,
) -> bool:
    target = _validated_request_id(target_request_id, "target_request_id")
    context = conn._build_v2_context(
        operation_name="Cancel request",
        request_id=request_id,
        require_credentials=False,
    )
    if context is None:
        return False
    envelope = context.to_envelope(
        "cancel_request",
        {"target_request_id": target},
    )
    conn.invoke_rpc(
        "invoke_v2_control",
        envelope,
        control=True,
        notification=True,
    )
    return True


def disconnect(conn) -> None:
    """Drop adapter authentication and close both transport lanes."""

    if not mark_connection_disconnected(conn):
        return
    seen: set[int] = set()
    first_error: BaseException | None = None
    for lane in (
        getattr(conn, "server", None),
        getattr(conn, "control_server", None),
    ):
        first_error = close_transport_lane(lane, seen, first_error)
    if first_error is not None:
        raise RpcInvocationError("disconnect", first_error) from None


def _validated_request_id(value: str, field_name: str) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"{field_name} must be a UUID") from exc
    if parsed.int == 0:
        raise ValueError(f"{field_name} must not be the nil UUID")
    return str(parsed)


def _authentication_required(operation: str) -> dict[str, Any]:
    return {
        "success": False,
        "error_code": "RPC_AUTHENTICATION_REQUIRED",
        "error": f"{operation} requires authenticated RPC v2",
    }


def _legacy_authority_removed() -> dict[str, Any]:
    return {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": "Document authority is owned by native FreeCAD collaboration.",
    }
