"""Session (Phase 7 / 7D server_ops)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from . import surfaces


def safe_diagnostic_code(value: Any, fallback: str) -> str:
    candidate = str(value or "")
    return candidate if surfaces.DIAGNOSTIC_CODE_RE.fullmatch(candidate) else fallback


def session_needs_refresh(*, margin_seconds: float = 60.0) -> bool:
    value = surfaces.state.rpc_session_expires_at
    if not value:
        return True
    try:
        expires = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return True
    return expires <= datetime.now(UTC) + timedelta(seconds=margin_seconds)
