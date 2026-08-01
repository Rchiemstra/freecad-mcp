"""FreeCADConnection method implementations."""

from __future__ import annotations

import logging
import time
from typing import Any

from ...telemetry import emit_event
from ..proxy_lane import ProxyLane

logger = logging.getLogger("FreeCADMCPserver")



def set_identity(
        conn,
        *,
        instance_id: str | None = None,
        client: str | None = None,
        pid: int | None = None,
        host: str | None = None,
    ) -> None:
        with conn._identity_lock:
            if instance_id is not None:
                conn._mcp_instance_id = instance_id
            if client is not None:
                conn._mcp_client = client
            if pid is not None:
                conn._mcp_pid = pid
            if host is not None:
                conn._mcp_host = host
            conn._refresh_headers()


def set_active_lease_token(conn, token: str | None) -> None:
        """Set the deprecated lease header for the current execution context.

        This API remains for v1 heartbeat/release callers. It no longer mutates
        shared connection state, so two threads cannot route one document's
        token onto another document's request.
        """

        conn._legacy_lease_token.set(token)


def _make_proxy(conn, timeout: float) -> ProxyLane:
        # Reuse the serialized general lane for the normal timeout. Longer
        # calls get an independent lane and cannot corrupt its transport.
        if timeout == conn._timeout:
            return conn.server
        return ProxyLane(
            conn._uri,
            timeout,
            conn._request_headers_snapshot,
        )


def invoke_rpc(
        conn,
        method: str,
        *args: Any,
        control: bool = False,
        timeout: float | None = None,
    ) -> Any:
        """Invoke a method on a serialized general or independent control lane."""

        started = time.monotonic()
        emit_event(
            "rpc_client",
            "rpc_invocation_started",
            payload={
                "method": method,
                "control_lane": bool(control),
                "custom_timeout": timeout,
            },
        )
        with conn._identity_lock:
            if conn._disconnected:
                raise RuntimeError("FreeCAD RPC connection is disconnected")
        try:
            if timeout is not None and timeout != conn._timeout and not control:
                lane = conn._make_proxy(timeout)
                try:
                    result = lane.call(method, *args)
                finally:
                    lane.close()
            else:
                lane = conn.control_server if control else conn.server
                result = lane.call(method, *args)
        except Exception as exc:
            emit_event(
                "rpc_client",
                "rpc_invocation_failed",
                status="failed",
                duration_ms=(time.monotonic() - started) * 1000.0,
                error_code=getattr(exc, "code", type(exc).__name__.upper()),
                payload={"method": method, "exception_type": type(exc).__name__},
            )
            raise
        emit_event(
            "rpc_client",
            "rpc_invocation_completed",
            duration_ms=(time.monotonic() - started) * 1000.0,
            payload={"method": method, "control_lane": bool(control)},
        )
        return result
