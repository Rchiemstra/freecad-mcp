"""FreeCADConnection method implementations."""

from __future__ import annotations

import logging
from collections.abc import Callable

from ...lease_manager import (
    LeaseClientManager,
    StaleLeaseRecoveryOrchestrator,
)

logger = logging.getLogger("FreeCADMCPserver")



def _refresh_headers(conn) -> None:
        with conn._identity_lock:
            headers: list[tuple[str, str]] = []
            if conn._mcp_instance_id:
                headers.append(("X-MCP-Instance-Id", str(conn._mcp_instance_id)))
            if conn._mcp_client:
                headers.append(("X-MCP-Client", str(conn._mcp_client)))
            if conn._mcp_pid:
                headers.append(("X-MCP-Pid", str(conn._mcp_pid)))
            if conn._mcp_host:
                headers.append(("X-MCP-Host", str(conn._mcp_host)))
            headers.append(("X-MCP-Rpc-Port", str(conn._rpc_port)))
            conn._base_headers = tuple(headers)


def configure_lease_routing(
        conn,
        manager: LeaseClientManager,
        document_session_resolver: Callable[[str], str | None],
    ) -> None:
        """Install request-scoped session/credential routing for typed v1 calls."""

        with conn._identity_lock:
            conn._lease_manager = manager
            conn._document_session_resolver = document_session_resolver


def configure_session_refresher(conn, refresher: Callable[[], None]) -> None:
        """Install a synchronized handshake refresh used only after auth rejection."""
        with conn._identity_lock:
            conn._session_refresher = refresher


def configure_stale_recovery(
        conn, orchestrator: StaleLeaseRecoveryOrchestrator
    ) -> None:
        """Install automatic stale-lease recovery orchestration for protected RPC."""

        with conn._identity_lock:
            conn._stale_recovery = orchestrator
