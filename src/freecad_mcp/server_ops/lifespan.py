"""Lifespan (Phase 7 / 7D server_ops)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..build_info import as_dict as build_info_dict
from ..telemetry.writer import close_default_writer, emit_event
from . import surfaces
from .session import safe_diagnostic_code


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:

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
            "MCP runtime identity: %s (pid=%s)",
            surfaces.state.mcp_instance_id,
            surfaces.state.mcp_pid,
        )
        # Do not connect to FreeCAD here: probing the RPC server can block for a
        # couple of seconds, which delays the MCP `initialize` handshake long
        # enough that clients with a short init timeout (e.g. the interactive
        # Cursor agent panel) mark the server as failed. The connection is
        # established lazily on first tool use via get_freecad_connection_impl().
        surfaces.logger.info("FreeCAD connection deferred until first tool use")
        yield {}
    finally:
        surfaces.state.rpc_session.close("MCP server shutdown")
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
            surfaces.state.rpc_session_id = None
            surfaces.state.rpc_session_expires_at = None
            surfaces.state.authenticated_manifest = None
        surfaces.logger.info("FreeCADMCP server shut down")
        emit_event(
            "mcp",
            "session_stopped",
            payload={
                "mcp_runtime_id": surfaces.state.mcp_instance_id,
                "held_document_count": 0,
            },
        )
        close_default_writer()
