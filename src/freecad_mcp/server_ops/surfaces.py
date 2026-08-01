"""§3.3 monkeypatch surfaces for server bootstrap."""

from __future__ import annotations

import re

LEASE_HEARTBEAT_INTERVAL_S = 10.0
DIAGNOSTIC_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def __getattr__(name: str):
    from freecad_mcp import server

    if name == "state":
        return server.state
    if name == "stale_recovery":
        return server.stale_recovery
    if name == "connection_lock":
        return server._connection_lock
    if name == "logger":
        return server.logger
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
