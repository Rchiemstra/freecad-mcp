"""Why the GUI thread is currently deferring MCP work.

The Qt guards run on the GUI thread and record the blocking widget they saw; the
timeout path runs on an RPC thread and must not touch Qt, so it only reads this
snapshot. A single tuple assignment keeps reads and writes atomic.
"""

from __future__ import annotations

_blocked_by: tuple[str, str] | None = None


def note_blocking_widget(kind: str, widget: object) -> None:
    title = ""
    getter = getattr(widget, "windowTitle", None)
    if callable(getter):
        try:
            title = str(getter() or "")
        except Exception:
            title = ""
    global _blocked_by
    _blocked_by = (kind, title)


def clear_gui_block() -> None:
    global _blocked_by
    _blocked_by = None


def describe_gui_block() -> str | None:
    blocked_by = _blocked_by
    if blocked_by is None:
        return None
    kind, title = blocked_by
    named = f" {title!r}" if title else ""
    return (
        f"FreeCAD GUI is blocked by an open {kind}{named}; "
        "MCP GUI work waits until it is closed in FreeCAD"
    )


__all__ = ["clear_gui_block", "describe_gui_block", "note_blocking_widget"]
