"""§3.3 late-bind surfaces for MCP tool modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .server_ops import surfaces

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState


def server_state() -> ServerState:
    return surfaces.state


def server_connection() -> FreeCADConnection:
    return surfaces.get_freecad_connection()


def server_stale_recovery() -> StaleLeaseRecoveryOrchestrator:
    return surfaces.stale_recovery
