"""§3.3 late-bind surfaces for MCP tool modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState


def server_state() -> ServerState:
    from freecad_mcp import server

    return server.state


def server_connection() -> FreeCADConnection:
    from freecad_mcp import server

    return server.get_freecad_connection()


def server_stale_recovery() -> StaleLeaseRecoveryOrchestrator:
    from freecad_mcp import server

    return server.stale_recovery
