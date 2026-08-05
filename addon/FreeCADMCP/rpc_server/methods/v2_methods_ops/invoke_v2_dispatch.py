"""Authenticated RPC dispatch body for invoke_v2."""
from __future__ import annotations

try:
    from ....dispatch.request_cancellation_error import RequestCancellationError
except ImportError:  # pragma: no cover - flat addon import path
    from dispatch.request_cancellation_error import RequestCancellationError

from .invoke_v2_finalize import finalize_invoke_v2_response


def register_invoke_v2_inflight(
    *,
    collaborators,
    self,
    session,
    envelope,
    target,
    replay_cache,
):
    """Bind envelope params and register the inflight request."""
    try:
        params = self._ordered_envelope_params(target, envelope.params)
        inflight = collaborators.inflight_request_registry.register(
            session.session_id,
            envelope.request_id,
            envelope.method,
        )
    except Exception:
        replay_cache.abandon(session.mcp.runtime_id, envelope)
        raise
    return params, inflight


def set_invoke_v2_request_identity(
    *,
    identity_provider,
    session,
    envelope,
    transport_identity,
):
    """Publish authenticated request identity for downstream RPC handlers."""
    identity_provider.set_request_identity(
        instance_id=session.mcp.runtime_id,
        client=session.mcp.client_build_id,
        pid=session.mcp.pid,
        host=session.mcp.hostname,
        rpc_port=transport_identity.get("rpc_port"),
        request_id=envelope.request_id,
        rpc_session_token=envelope.session_token,
        mcp_process_started_at=session.mcp.process_started_at,
        agent_id=(
            envelope.operation.task_id
            if envelope.operation and envelope.operation.task_id
            else None
        ),
        authenticated_session_id=session.session_id,
    )


def run_invoke_v2_dispatch(
    *,
    collaborators,
    self,
    session,
    envelope,
    params,
    inflight,
    invocation_runtime_id: str,
    replay_cache,
    handler_state: dict,
):
    """Dispatch one authenticated envelope and finalize replay state."""
    dispatch_started = False
    try:
        inflight.token.checkpoint("dispatch")
        dispatch_started = True
        result = self._dispatch(envelope.method, params)
        cancellation = inflight.token.snapshot()
        if cancellation.cancellation_requested:
            resolution = self._complete_request_cancellation(
                inflight,
                dirty=(True if cancellation.mutation_started else None),
            )
            result = {
                "success": False,
                "error_code": (
                    "REQUEST_CANCELLED_AFTER_MUTATION"
                    if cancellation.mutation_started or cancellation.uncertain
                    else "REQUEST_CANCELLED"
                ),
                "error": "Authenticated request was cancelled",
                "cancellation": cancellation.to_public_dict(),
                "cancellation_resolution": resolution,
            }
        response = {
            "ok": not (
                isinstance(result, dict)
                and (result.get("success") is False or result.get("ok") is False)
            ),
            "request_id": envelope.request_id,
            "addon_runtime_id": invocation_runtime_id,
            "result": result,
        }
        cached_response = response
        handler_status = (
            "cancelled"
            if inflight.token.snapshot().cancellation_requested
            else ("completed" if response["ok"] else "failed")
        )
        result_code = (
            str(result.get("error_code") or result.get("code") or "")
            if isinstance(result, dict)
            else ""
        )
        process_pinned = bool(
            cancellation.uncertain
            or (
                isinstance(result, dict)
                and bool(result.get("completion_uncertain"))
            )
            or result_code
            in {
                "GUI_COMPLETION_UNCERTAIN",
                "REQUEST_CANCELLED_AFTER_MUTATION",
                "REQUEST_OUTCOME_UNCERTAIN",
            }
        )
        return finalize_invoke_v2_response(
            collaborators=collaborators,
            self=self,
            session=session,
            envelope=envelope,
            inflight=inflight,
            invocation_runtime_id=invocation_runtime_id,
            replay_cache=replay_cache,
            outbound=response,
            cached=cached_response,
            status=handler_status,
            handler_state=handler_state,
            process_pinned=process_pinned,
        )
    except RequestCancellationError as exc:
        resolution = self._complete_request_cancellation(inflight)
        response = {
            "ok": False,
            "request_id": envelope.request_id,
            "addon_runtime_id": invocation_runtime_id,
            "result": {
                "success": False,
                "error_code": (
                    "REQUEST_CANCELLED_AFTER_MUTATION"
                    if exc.snapshot.mutation_started or exc.snapshot.uncertain
                    else "REQUEST_CANCELLED"
                ),
                "error": str(exc),
                "cancellation": exc.snapshot.to_public_dict(),
                "cancellation_resolution": resolution,
            },
        }
        handler_status = "cancelled"
        return finalize_invoke_v2_response(
            collaborators=collaborators,
            self=self,
            session=session,
            envelope=envelope,
            inflight=inflight,
            invocation_runtime_id=invocation_runtime_id,
            replay_cache=replay_cache,
            outbound=response,
            cached=response,
            status=handler_status,
            handler_state=handler_state,
            process_pinned=bool(
                exc.snapshot.mutation_started or exc.snapshot.uncertain
            ),
        )
    except Exception:
        if dispatch_started:
            uncertainty_response = {
                "ok": False,
                "request_id": envelope.request_id,
                "addon_runtime_id": invocation_runtime_id,
                "error": {
                    "code": "REQUEST_OUTCOME_UNCERTAIN",
                    "message": (
                        "The authenticated request outcome is uncertain; "
                        "the same request ID will not be dispatched again"
                    ),
                },
            }
            handler_status = "uncertain"
            return finalize_invoke_v2_response(
                collaborators=collaborators,
                self=self,
                session=session,
                envelope=envelope,
                inflight=inflight,
                invocation_runtime_id=invocation_runtime_id,
                replay_cache=replay_cache,
                outbound=uncertainty_response,
                cached=uncertainty_response,
                status=handler_status,
                handler_state=handler_state,
                process_pinned=True,
            )
        replay_cache.abandon(session.mcp.runtime_id, envelope)
        raise
    finally:
        if not handler_state["finalized"]:
            failed_terminal = collaborators.inflight_request_registry.finish_handler(
                session.session_id,
                envelope.request_id,
                status=handler_state["status"],
            )
            if (
                failed_terminal is not None
                and failed_terminal.cancellation_requested
                and not failed_terminal.cancellation_resolved
            ):
                self._complete_request_cancellation(
                    inflight,
                    dirty=(
                        True
                        if failed_terminal.mutation_started or failed_terminal.uncertain
                        else None
                    ),
                )
                collaborators.inflight_request_registry.finish_handler(
                    session.session_id,
                    envelope.request_id,
                    status="cancelled",
                )
