"""Heartbeat (Phase 7 / 7D server_ops)."""

from __future__ import annotations

import asyncio
import random

from ..lease_manager import STALE_RECOVERY_TRIGGER_HEARTBEAT
from . import surfaces
from .session import safe_diagnostic_code
from .stale_recovery_hooks import reconcile_stale_sessions


async def lease_heartbeat_loop() -> None:
    """Renew every held lease while this MCP process owns it."""

    while True:
        await asyncio.sleep(surfaces.LEASE_HEARTBEAT_INTERVAL_S * random.uniform(0.8, 1.2))
        await lease_heartbeat_once()


async def lease_heartbeat_once() -> bool:
    """Run one atomic, redacted renewal attempt for focused testing/recovery."""

    if (
        not surfaces.state.lease_manager.credentials_snapshot()
        or surfaces.state.freecad_connection is None
        or not surfaces.state.lease_manager.connected
    ):
        return False
    conn = surfaces.state.freecad_connection
    try:
        from freecad_mcp import server

        with surfaces.connection_lock:
            server._authenticate_connection(conn)
        payload, context = surfaces.state.lease_manager.build_heartbeat_request()
        response = await asyncio.to_thread(
            conn.heartbeat_document_locks_batch, payload, context
        )
        if not isinstance(response, dict):
            surfaces.logger.warning("Lease heartbeat returned a malformed response")
            return False
        result = response.get("result", response)
        if isinstance(result, dict):
            surfaces.state.lease_manager.apply_heartbeat_response(result)
            stale_sessions = surfaces.stale_recovery.observe_heartbeat_batch(result)
            if stale_sessions:
                await reconcile_stale_sessions(
                    stale_sessions, STALE_RECOVERY_TRIGGER_HEARTBEAT
                )
        successful = bool(
            response.get(
                "ok",
                result.get("success", False) if isinstance(result, dict) else False,
            )
        )
        if not successful:
            error = response.get("error")
            error_code = (
                error.get("code")
                if isinstance(error, dict)
                else result.get("error_code")
                if isinstance(result, dict)
                else None
            )
            surfaces.logger.warning(
                "Lease heartbeat batch failed (code=%s)",
                safe_diagnostic_code(error_code, "UNKNOWN_HEARTBEAT_ERROR"),
            )
        return successful
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Never interpolate remote exception text: an XML-RPC peer can place
        # credentials in fault messages. The class/code is enough for routine
        # heartbeat diagnostics and leaves raw tokens out of logs.
        error_code = getattr(exc, "code", type(exc).__name__)
        surfaces.logger.warning(
            "Lease heartbeat batch error (code=%s)",
            safe_diagnostic_code(error_code, "HEARTBEAT_EXCEPTION"),
        )
        return False
