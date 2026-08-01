"""Stale Recovery Hooks (Phase 7 / 7D server_ops)."""

from __future__ import annotations

from ..lease_manager import STALE_RECOVERY_TRIGGER_POST_TOOL
from . import surfaces


async def reconcile_stale_sessions(
    session_uuids: tuple[str, ...] | list[str],
    trigger: str,
) -> None:
    if not session_uuids:
        return
    conn = surfaces.state.freecad_connection
    if conn is None or not surfaces.state.lease_manager.connected:
        return
    try:
        await surfaces.stale_recovery.recover_sessions(
            session_uuids,
            trigger,
            conn.reconcile_document_lease,
        )
    except Exception as exc:
        surfaces.logger.warning(
            "Stale lease recovery orchestration failed (%s)",
            type(exc).__name__,
        )


async def post_tool_stale_recovery(duration_s: float, tool_name: str) -> None:
    del tool_name
    try:
        if duration_s < surfaces.stale_recovery.stale_after_seconds:
            return
        sessions = tuple(
            credential.document_session_uuid
            for credential in surfaces.state.lease_manager.credentials_snapshot()
        )
        affected = surfaces.stale_recovery.observe_tool_completion(duration_s, sessions)
        if affected:
            await reconcile_stale_sessions(
                affected, STALE_RECOVERY_TRIGGER_POST_TOOL
            )
    except Exception as exc:
        surfaces.logger.warning(
            "Post-tool stale lease recovery failed (%s)",
            type(exc).__name__,
        )
