"""Frozen compatibility hooks for the removed document-lease heartbeat."""

from __future__ import annotations


async def lease_heartbeat_loop() -> None:
    """Return immediately; native FreeCAD owns document mutation semantics."""


async def lease_heartbeat_once() -> bool:
    """Report that no heartbeat was attempted."""

    return False
