"""Helpers for authenticated invoke_v2 transport and session refresh."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...lease_manager import RpcRequestContext
from ...mcp_tasks import link_runtime
from ...telemetry import emit_event
from ...telemetry.context import get_context, update_context
from ..generated_execute import _sign_generated_execute_params
from ..rpc_invocation_error import RpcInvocationError

_ACQUISITION_METHODS = frozenset(
    {
        "acquire_document_lock",
        "adopt_dirty_document",
        "create_document",
    }
)
_SESSION_EXPIRED_CODES = frozenset({"SESSION_EXPIRED", "UNKNOWN_SESSION"})


def _redact_native_remote_error(
    conn,
    error: Exception,
    context: RpcRequestContext,
) -> Exception:
    """Preserve a native error while scrubbing active session/lease secrets."""

    from ..._shared.protocol.json_rpc_client import JsonRpcRemoteError

    secrets = (
        context.session_token,
        *(item.token for item in context.lease_credentials),
    )
    payload = {"message": error.message, "data": error.data}
    manager = getattr(conn, "__dict__", {}).get("_lease_manager")
    redact_value = getattr(manager, "redact_value", None)
    if callable(redact_value):
        safe = redact_value(payload, additional_secrets=secrets)
    else:

        def scrub(value: Any) -> Any:
            if isinstance(value, str):
                safe_text = value
                for secret in secrets:
                    if secret:
                        safe_text = safe_text.replace(secret, "[REDACTED]")
                return safe_text
            if isinstance(value, Mapping):
                return {str(key): scrub(item) for key, item in value.items()}
            if isinstance(value, tuple):
                return tuple(scrub(item) for item in value)
            if isinstance(value, list):
                return [scrub(item) for item in value]
            return value

        safe = scrub(payload)
    if safe == payload:
        return error
    return JsonRpcRemoteError(
        error.code,
        str(safe["message"]),
        data=safe["data"],
        request_id=error.request_id,
    )


def invoke_v2_execution_category(method: str, params: Mapping[str, Any] | None) -> str:
    if method != "execute_code" or not isinstance(params, Mapping):
        return "typed_direct_rpc"
    options = params.get("options")
    if not isinstance(options, Mapping):
        return "public_execute_code"
    if options.get("generated_operation"):
        return "generated_internal_execute"
    if options.get("read_only"):
        return "read_only_worker_analysis"
    return "public_execute_code"


def invoke_v2_prepare_telemetry(
    context: RpcRequestContext,
    *,
    method: str,
    control: bool,
    category: str,
) -> str:
    document_sessions = tuple(
        item.document_session_uuid for item in context.lease_credentials
    )
    update_context(
        request_id=context.request_id,
        execution_id=context.request_id,
        task_id=context.task_id or None,
        document_session_uuid=(
            document_sessions[0] if len(document_sessions) == 1 else None
        ),
        execution_category=category,
    )
    task_context_id = get_context().task_id
    if task_context_id:
        link_runtime(task_context_id, request_id=context.request_id)
    emit_event(
        "rpc_client",
        "routing_completed",
        payload={
            "method": method,
            "execution_category": category,
            "document_session_uuids": list(document_sessions),
            "control_lane": bool(control),
        },
    )
    return task_context_id


def invoke_v2_transport(
    conn,
    method: str,
    params: Mapping[str, Any] | None,
    context: RpcRequestContext,
    *,
    control: bool,
    timeout: float | None,
) -> dict[str, Any]:
    from ..._shared.protocol.json_rpc_client import JsonRpcRemoteError

    wire_params = _sign_generated_execute_params(method, params, context)
    envelope = context.to_envelope(method, wire_params)
    transport_method = "invoke_v2_control" if control else "invoke_v2"
    conn._maybe_recover_stale_before_protected_rpc(method, context)
    try:
        return conn.invoke_rpc(
            transport_method,
            envelope,
            control=control,
            timeout=timeout,
        )
    except JsonRpcRemoteError as exc:
        raise _redact_native_remote_error(conn, exc, context) from None
    except Exception as exc:
        if not control and method in _ACQUISITION_METHODS:
            recovered = conn._recover_acquisition_after_transport_loss(
                method,
                context.request_id,
                params=params,
            )
            if recovered is not None:
                return recovered
        raise RpcInvocationError(method, exc, request_id=context.request_id) from None


def invoke_v2_update_runtime_links(
    response: Mapping[str, Any],
    *,
    task_context_id: str,
    request_id: str,
) -> None:
    result = response.get("result")
    candidates = [response, result] if isinstance(result, Mapping) else [response]
    for candidate in candidates:
        execution = candidate.get("execution")
        worker_job_id = candidate.get("worker_job_id") or candidate.get("job_id")
        if isinstance(execution, Mapping):
            worker_job_id = worker_job_id or execution.get("job_id")
        recovery_incident_id = candidate.get("recovery_incident_id")
        updates: dict[str, Any] = {}
        if worker_job_id:
            updates["worker_job_id"] = worker_job_id
            if task_context_id:
                link_runtime(
                    task_context_id,
                    request_id=request_id,
                    worker_job_id=str(worker_job_id),
                )
        if recovery_incident_id:
            updates["recovery_incident_id"] = recovery_incident_id
        if updates:
            update_context(**updates)


def invoke_v2_session_error_code(response: Mapping[str, Any]) -> str | None:
    error = response.get("error")
    if not isinstance(error, Mapping):
        return None
    error_code = error.get("code")
    return str(error_code) if error_code is not None else None


def invoke_v2_retry_expired_session(
    conn,
    method: str,
    params: Mapping[str, Any] | None,
    context: RpcRequestContext,
    *,
    response: Mapping[str, Any],
    transport_method: str,
    control: bool,
    timeout: float | None,
) -> dict[str, Any]:
    from ..._shared.protocol.json_rpc_client import JsonRpcRemoteError

    with conn._identity_lock:
        refresher = conn._session_refresher
        manager = conn._lease_manager
    if refresher is None or manager is None:
        return response
    try:
        refresher()
    except Exception as exc:
        raise RpcInvocationError(method, exc, request_id=context.request_id) from None

    refreshed = manager.build_request_context(
        document_session_uuids=tuple(
            item.document_session_uuid for item in context.lease_credentials
        ),
        operation_name=context.operation_name,
        task_id=context.task_id,
        request_id=context.request_id,
    )
    refreshed_params = _sign_generated_execute_params(method, params, refreshed)
    try:
        return conn.invoke_rpc(
            transport_method,
            refreshed.to_envelope(method, refreshed_params),
            control=control,
            timeout=timeout,
        )
    except JsonRpcRemoteError as exc:
        raise _redact_native_remote_error(conn, exc, refreshed) from None
    except Exception as exc:
        raise RpcInvocationError(method, exc, request_id=context.request_id) from None


def invoke_v2_retry_expired_remote_error(
    conn,
    method: str,
    params: Mapping[str, Any] | None,
    context: RpcRequestContext,
    *,
    remote_error: Exception,
    transport_method: str,
    control: bool,
    timeout: float | None,
) -> dict[str, Any]:
    """Refresh once for a native session-expiry error, otherwise preserve it."""

    from ..._shared.protocol.json_rpc_client import JsonRpcRemoteError

    with conn._identity_lock:
        refresher = conn._session_refresher
        manager = conn._lease_manager
    if refresher is None or manager is None:
        raise remote_error
    try:
        refresher()
    except Exception as exc:
        raise RpcInvocationError(method, exc, request_id=context.request_id) from None
    refreshed = manager.build_request_context(
        document_session_uuids=tuple(
            item.document_session_uuid for item in context.lease_credentials
        ),
        operation_name=context.operation_name,
        task_id=context.task_id,
        request_id=context.request_id,
    )
    refreshed_params = _sign_generated_execute_params(method, params, refreshed)
    try:
        return conn.invoke_rpc(
            transport_method,
            refreshed.to_envelope(method, refreshed_params),
            control=control,
            timeout=timeout,
        )
    except JsonRpcRemoteError as exc:
        raise _redact_native_remote_error(conn, exc, refreshed) from None
    except Exception as exc:
        raise RpcInvocationError(method, exc, request_id=context.request_id) from None
