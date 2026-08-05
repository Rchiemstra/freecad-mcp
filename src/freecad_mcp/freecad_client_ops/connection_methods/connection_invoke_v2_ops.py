"""FreeCADConnection method implementations."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from ..._shared.protocol.json_rpc_client import JsonRpcRemoteError
from ...rpc_session import RpcAuthenticationContext
from .connection_invoke_v2_helpers import (
    _SESSION_EXPIRED_CODES,
    invoke_v2_execution_category,
    invoke_v2_prepare_telemetry,
    invoke_v2_retry_expired_remote_error,
    invoke_v2_retry_expired_session,
    invoke_v2_session_error_code,
    invoke_v2_transport,
    invoke_v2_update_runtime_links,
)

logger = logging.getLogger("FreeCADMCPserver")


def invoke_v2(
    conn,
    method: str,
    params: Mapping[str, Any] | None,
    context: RpcAuthenticationContext,
    *,
    control: bool = False,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Send one immutable v2 envelope without shared credential headers."""

    if not isinstance(context, RpcAuthenticationContext):
        session = conn._v2_auth_session()
        if session is None:
            raise TypeError("context must be an RpcAuthenticationContext")
        context = session.build_request_context(
            operation_name=str(getattr(context, "operation_name", "") or ""),
            task_id=str(getattr(context, "task_id", "") or ""),
            request_id=str(getattr(context, "request_id", "") or "") or None,
        )

    category = invoke_v2_execution_category(method, params)
    task_context_id = invoke_v2_prepare_telemetry(
        context,
        method=method,
        control=control,
        category=category,
    )
    try:
        response = invoke_v2_transport(
            conn,
            method,
            params,
            context,
            control=control,
            timeout=timeout,
        )
    except JsonRpcRemoteError as exc:
        if exc.semantic_code not in _SESSION_EXPIRED_CODES:
            raise
        transport_method = "invoke_v2_control" if control else "invoke_v2"
        return invoke_v2_retry_expired_remote_error(
            conn,
            method,
            params,
            context,
            remote_error=exc,
            transport_method=transport_method,
            control=control,
            timeout=timeout,
        )
    if isinstance(response, Mapping):
        invoke_v2_update_runtime_links(
            response,
            task_context_id=task_context_id,
            request_id=context.request_id,
        )
    error_code = (
        invoke_v2_session_error_code(response)
        if isinstance(response, Mapping)
        else None
    )
    if error_code not in _SESSION_EXPIRED_CODES:
        return response
    transport_method = "invoke_v2_control" if control else "invoke_v2"
    return invoke_v2_retry_expired_session(
        conn,
        method,
        params,
        context,
        response=response,
        transport_method=transport_method,
        control=control,
        timeout=timeout,
    )
