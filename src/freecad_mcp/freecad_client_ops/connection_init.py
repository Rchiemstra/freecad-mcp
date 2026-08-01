"""FreeCADConnection constructor."""

from __future__ import annotations

import contextvars
import threading
from collections.abc import Callable
from typing import Any

from ..lease_manager import LeaseClientManager, StaleLeaseRecoveryOrchestrator
from .proxy_lane import ProxyLane


def init_connection(
    conn,
    host: str = "localhost",
    port: int = 9875,
    timeout: float = 150,
    expected_instance_id: str | None = None,
    mcp_instance_id: str | None = None,
    mcp_client: str | None = None,
    mcp_pid: int | None = None,
    mcp_host: str | None = None,
):
    conn._uri = f"http://{host}:{port}"
    conn._timeout = timeout
    conn._expected_instance_id = expected_instance_id
    conn._mcp_instance_id = mcp_instance_id
    conn._mcp_client = mcp_client
    conn._mcp_pid = mcp_pid
    conn._mcp_host = mcp_host
    conn._rpc_port = port
    conn._identity_lock = threading.RLock()
    conn._base_headers: tuple[tuple[str, str], ...] = ()
    conn._lease_manager: LeaseClientManager | None = None
    conn._document_session_resolver: Callable[[str], str | None] | None = None
    conn._session_refresher: Callable[[], None] | None = None
    conn._rpc_method_capabilities: dict[str, Any] = {}
    conn._rpc_method_capabilities_loaded = False
    conn._legacy_lease_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
        f"freecad_mcp_legacy_lease_token_{id(conn)}", default=None
    )
    conn._refresh_headers()
    conn.server = ProxyLane(conn._uri, timeout, conn._request_headers_snapshot)
    conn.control_server = ProxyLane(
        conn._uri,
        min(timeout, 30),
        conn._request_headers_snapshot,
    )
    conn._transport = conn.server.transport
    conn._disconnected = False
    conn._stale_recovery: StaleLeaseRecoveryOrchestrator | None = None
