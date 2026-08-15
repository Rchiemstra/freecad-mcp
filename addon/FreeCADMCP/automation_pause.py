"""Local-user pause gate for remote MCP document writes.

The toggle is deliberately not exposed as an RPC method.  A user presses the
Document Lock dock control; already admitted requests retain their admission
and may finish, while later remote writes receive ``AUTOMATION_PAUSED``.
"""

from __future__ import annotations

from collections.abc import Iterable
from threading import RLock
from typing import Any
from uuid import uuid4

try:
    from automation_pause_ui_bridge import request_local_pause_refresh
except ImportError:  # pragma: no cover - package test layout
    from addon.FreeCADMCP.automation_pause_ui_bridge import request_local_pause_refresh


_lock = RLock()
_paused = False
_active: dict[str, dict[str, Any]] = {}
_last_finished: dict[str, Any] | None = None


def _queue_local_gui_refresh() -> None:
    """Request presentation refresh through the neutral local GUI bridge."""

    request_local_pause_refresh()


def request_local_pause_after_current() -> dict[str, Any]:
    """Stop admission of future remote writes; current requests are untouched."""

    global _paused
    with _lock:
        _paused = True
        result = status()
    _queue_local_gui_refresh()
    return result


def resume_local_agent_writes() -> dict[str, Any]:
    """Resume remote write admission after an explicit local GUI action."""

    global _paused
    with _lock:
        _paused = False
        result = status()
    _queue_local_gui_refresh()
    return result


def admit_remote_write(method: str, document_names: Iterable[str] = ()) -> dict[str, Any]:
    """Return an admission token or a public, non-mutating pause refusal."""

    with _lock:
        if _paused:
            return {
                "success": False,
                "error_code": "AUTOMATION_PAUSED",
                "error": "Local user paused new MCP writes; active work may finish.",
                "automation_pause": status(),
            }
        token = str(uuid4())
        _active[token] = {
            "method": str(method),
            "documents": tuple(
                name for name in (str(item) for item in document_names) if name
            ),
        }
        result = {"success": True, "token": token}
    _queue_local_gui_refresh()
    return result


def finish_remote_write(token: str | None) -> None:
    global _last_finished
    if not token:
        return
    with _lock:
        finished = _active.pop(str(token), None)
        if finished is not None:
            _last_finished = dict(finished)
    _queue_local_gui_refresh()


def status() -> dict[str, Any]:
    """Read-only state safe for RPC readiness and GUI presentation."""

    with _lock:
        operations = [dict(item) for item in _active.values()]
        current = operations[0] if operations else None
        return {
            "paused": _paused,
            "pause_after_current": _paused and bool(operations),
            "active_write_count": len(operations),
            "current_operation": current,
            "current_operations": operations,
            "last_operation": dict(_last_finished) if _last_finished else None,
        }


__all__ = [
    "admit_remote_write",
    "finish_remote_write",
    "request_local_pause_after_current",
    "resume_local_agent_writes",
    "status",
]
