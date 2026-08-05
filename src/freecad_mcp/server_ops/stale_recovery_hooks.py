"""Frozen compatibility hooks for removed lease-recovery orchestration."""

from __future__ import annotations


async def reconcile_stale_sessions(
    session_uuids: tuple[str, ...] | list[str],
    trigger: str,
) -> None:
    del session_uuids, trigger


async def post_tool_stale_recovery(duration_s: float, tool_name: str) -> None:
    del duration_s, tool_name
