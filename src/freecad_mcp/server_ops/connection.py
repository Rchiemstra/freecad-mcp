"""Connection (Phase 7 / 7D server_ops)."""

from __future__ import annotations

from ..freecad_client import FreeCADConnection
from . import surfaces


def get_freecad_connection() -> FreeCADConnection:
    """Get or create a persistent FreeCAD connection."""
    with surfaces.connection_lock:
        if surfaces.state.freecad_connection is not None:
            surfaces.authenticate_connection(surfaces.state.freecad_connection)
            return surfaces.state.freecad_connection

        conn = surfaces.freecad_connection_factory(
            host=surfaces.state.rpc_host,
            port=surfaces.state.rpc_port,
            expected_instance_id=surfaces.state.instance_id,
            mcp_instance_id=surfaces.state.mcp_instance_id,
            mcp_client=surfaces.state.mcp_client_label,
            mcp_pid=surfaces.state.mcp_pid or None,
            mcp_host=surfaces.state.mcp_host or None,
        )
        try:
            if not conn.ping():
                surfaces.logger.error("Failed to ping FreeCAD")
                raise Exception(
                    "Failed to connect to FreeCAD. Make sure the FreeCAD addon is running."
                )
            if surfaces.state.instance_id:
                conn.verify_instance()
            if surfaces.state.instance_manifest is not None:
                surfaces.authenticate_connection(conn, force=True)
        except Exception:
            surfaces.state.rpc_session.mark_disconnected(
                "FreeCAD connection initialization failed"
            )
            conn.disconnect()
            raise
        surfaces.state.freecad_connection = conn
        return conn
