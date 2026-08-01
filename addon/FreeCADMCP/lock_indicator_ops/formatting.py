from __future__ import annotations

from typing import Any


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _bounded_text(value: Any, *, limit: int = 160) -> str:
    """Return single-line diagnostic text suitable for the UI."""

    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[: max(0, limit - 1)] + "…"
    return text
