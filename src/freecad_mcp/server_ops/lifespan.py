"""Lifespan (Phase 7 / 7D server_ops)."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..build_info import as_dict as build_info_dict
from ..telemetry import close_default_writer, emit_event
from . import surfaces
from .heartbeat import lease_heartbeat_loop
from .session import safe_diagnostic_code


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:

    heartbeat_task = None
    try:
        surfaces.logger.info("FreeCADMCP server starting up")
        emit_event(
            "mcp",
            "session_started",
            payload={
                "mcp": {
                    **build_info_dict(),
                    "pid": surfaces.state.mcp_pid or os.getpid(),
                    "runtime_id": surfaces.state.mcp_instance_id,
                },
                "rpc_endpoint": {
                    "host": surfaces.state.rpc_host,
                    "port": surfaces.state.rpc_port,
                },
            },
        )
        surfaces.logger.info(
            "MCP lease identity: %s (pid=%s)",
            surfaces.state.mcp_instance_id,
            surfaces.state.mcp_pid,
        )
        # Do not connect to FreeCAD here: probing the RPC server can block for a
        # couple of seconds, which delays the MCP `initialize` handshake long
        # enough that clients with a short init timeout (e.g. the interactive
        # Cursor agent panel) mark the server as failed. The connection is
        # established lazily on first tool use via get_freecad_connection_impl().
        surfaces.logger.info("FreeCAD connection deferred until first tool use")
        heartbeat_task = asyncio.create_task(lease_heartbeat_loop())
        surfaces.stale_recovery.bind_event_loop(asyncio.get_running_loop())
        yield {}
    finally:
        # Fence session refresh and new credential storage before cancelling
        # background work. A late handshake or acquisition result cannot revive
        # the manager while the transports are closing.
        surfaces.state.lease_manager.close("MCP server shutdown")
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                surfaces.logger.warning(
                    "Lease heartbeat shutdown error (code=%s)",
                    safe_diagnostic_code(
                        getattr(exc, "code", type(exc).__name__),
                        "HEARTBEAT_SHUTDOWN_EXCEPTION",
                    ),
                )
        try:
            if surfaces.state.freecad_connection:
                surfaces.logger.info("Disconnecting from FreeCAD on shutdown")
                surfaces.state.freecad_connection.disconnect()
        except Exception as exc:
            surfaces.logger.warning(
                "FreeCAD disconnect error during shutdown (code=%s)",
                safe_diagnostic_code(
                    getattr(exc, "code", type(exc).__name__),
                    "DISCONNECT_EXCEPTION",
                ),
            )
        finally:
            surfaces.state.freecad_connection = None
            surfaces.state.lease_tokens.clear()
            surfaces.state.legacy_document_keys.clear()
            surfaces.state.document_sessions.clear()
            surfaces.state.rpc_session_id = None
            surfaces.state.rpc_session_expires_at = None
            surfaces.state.authenticated_manifest = None
        surfaces.logger.info("FreeCADMCP server shut down")
        emit_event(
            "mcp",
            "session_stopped",
            payload={
                "mcp_runtime_id": surfaces.state.mcp_instance_id,
                "held_document_count": len(surfaces.state.document_sessions),
            },
        )
        close_default_writer()
