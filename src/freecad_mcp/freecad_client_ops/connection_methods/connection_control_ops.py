"""FreeCADConnection method implementations."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import Any

from ...lease_manager import (
    RpcRequestContext,
)
from ..rpc_invocation_error import RpcInvocationError
from .connection_disconnect_helpers import close_transport_lane, mark_connection_disconnected

logger = logging.getLogger("FreeCADMCPserver")



def heartbeat_document_locks_batch(
        conn,
        payload: Mapping[str, Any],
        context: RpcRequestContext,
    ) -> dict[str, Any]:
        """Renew leases through the dedicated control transport."""

        return conn.invoke_v2(
            "lease_heartbeat_batch",
            payload,
            context,
            control=True,
        )


def reconcile_document_lease(
        conn,
        document_session_uuid: str,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Attempt exact-owner stale reconciliation on the control lane."""

        manager = conn._v2_lease_manager()
        if manager is None:
            return {
                "success": False,
                "error_code": "LEASE_PROTOCOL_REQUIRED",
                "error": "Lease reconciliation requires authenticated RPC v2",
            }
        credential = manager.require(document_session_uuid=document_session_uuid)
        scoped = manager.build_request_context(
            document_session_uuids=(document_session_uuid,),
            operation_name="Reconcile stale document lease",
            request_id=request_id,
        )
        response = conn.invoke_v2(
            "lease_reconcile",
            {"credential": credential.to_wire()},
            scoped,
            control=True,
        )
        return conn._unwrap_v2_response(
            response,
            additional_secrets=(scoped.session_token, credential.token),
        )


def get_request_status(
        conn,
        target_request_id: str,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Query completion after a timeout without replaying the mutation."""

        try:
            parsed_target_request_id = uuid.UUID(str(target_request_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("target_request_id must be a UUID") from exc
        if parsed_target_request_id.int == 0:
            raise ValueError("target_request_id must not be the nil UUID")
        target_request_id = str(parsed_target_request_id)
        context = conn._build_v2_context(
            operation_name="Get request status",
            request_id=request_id,
            require_credentials=False,
        )
        if context is None:
            return {
                "success": False,
                "error_code": "LEASE_PROTOCOL_REQUIRED",
                "error": "Request status requires authenticated RPC v2",
            }
        response = conn.invoke_v2(
            "get_request_status",
            {"request_id": target_request_id},
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
        """Claim a lost acquire/adopt/create credential exactly once."""

        try:
            parsed_target_request_id = uuid.UUID(str(target_request_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("target_request_id must be a UUID") from exc
        if parsed_target_request_id.int == 0:
            raise ValueError("target_request_id must not be the nil UUID")
        target_request_id = str(parsed_target_request_id)
        context = conn._build_v2_context(
            operation_name="Claim acquisition result",
            request_id=request_id,
            require_credentials=False,
        )
        if context is None:
            return {
                "success": False,
                "error_code": "LEASE_PROTOCOL_REQUIRED",
                "error": "Acquisition claim requires authenticated RPC v2",
            }
        response = conn.invoke_v2(
            "claim_acquisition_result",
            {"request_id": target_request_id},
            context,
            control=True,
        )
        return conn._unwrap_v2_response(
            response,
            additional_secrets=(context.session_token,),
        )


def acknowledge_acquisition_claim(
        conn,
        target_request_id: str,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Acknowledge custody of a claimed acquisition credential."""

        try:
            parsed_target_request_id = uuid.UUID(str(target_request_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("target_request_id must be a UUID") from exc
        if parsed_target_request_id.int == 0:
            raise ValueError("target_request_id must not be the nil UUID")
        target_request_id = str(parsed_target_request_id)
        context = conn._build_v2_context(
            operation_name="Acknowledge acquisition claim",
            request_id=request_id,
            require_credentials=False,
        )
        if context is None:
            return {
                "success": False,
                "error_code": "LEASE_PROTOCOL_REQUIRED",
                "error": "Acquisition acknowledgement requires authenticated RPC v2",
            }
        response = conn.invoke_v2(
            "acknowledge_acquisition_claim",
            {"request_id": target_request_id},
            context,
            control=True,
        )
        return conn._unwrap_v2_response(
            response,
            additional_secrets=(context.session_token,),
        )


def cancel_request(
        conn,
        target_request_id: str,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancel an owned v2 request through the reserved control lane.

        This low-level recovery primitive is intentionally not exposed as a
        model-facing MCP tool.
        """

        try:
            parsed_target_request_id = uuid.UUID(str(target_request_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("target_request_id must be a UUID") from exc
        if parsed_target_request_id.int == 0:
            raise ValueError("target_request_id must not be the nil UUID")
        target_request_id = str(parsed_target_request_id)
        context = conn._build_v2_context(
            operation_name="Cancel request",
            request_id=request_id,
            require_credentials=False,
        )
        if context is None:
            return {
                "success": False,
                "error_code": "LEASE_PROTOCOL_REQUIRED",
                "error": "Request cancellation requires authenticated RPC v2",
            }
        response = conn.invoke_v2(
            "cancel_request",
            {"target_request_id": target_request_id},
            context,
            control=True,
        )
        return conn._unwrap_v2_response(
            response,
            additional_secrets=(context.session_token,),
        )


def disconnect(conn) -> None:
        """Close both lanes. Lease release remains an explicit lifecycle step."""

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
