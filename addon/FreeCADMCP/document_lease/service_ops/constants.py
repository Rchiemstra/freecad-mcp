"""Shared constants and text helpers for document lease service operations."""

from __future__ import annotations

from collections.abc import Iterable

from ..model import LeaseState, token_fingerprint

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 10.0
DEFAULT_SIDECAR_HEARTBEAT_INTERVAL_SECONDS = 30.0
DEFAULT_STALE_AFTER_SECONDS = 90.0
# MCP runtime identity currently records a timestamp produced *inside* the
# process, which may be later than its OS creation time. A probed process that
# started materially after that marker must therefore be a PID reuse. The
# tolerance keeps small timestamp/precision differences fail-closed.
MCP_PROCESS_START_FUTURE_TOLERANCE_SECONDS = 1.0


IDENTITY_REFRESHABLE_STATES = frozenset(
    {
        LeaseState.ACQUIRING,
        LeaseState.LOCKED_IDLE,
        LeaseState.LOCKED_EDITING,
        LeaseState.LOCKED_RECOMPUTING,
        LeaseState.LOCKED_SAVING,
        LeaseState.LOCKED_ERROR,
        LeaseState.STALE,
        LeaseState.USER_INTERVENED,
        LeaseState.UNLOCKED_DIRTY,
    }
)

RECOVERY_IDENTITY_REFRESHABLE_STATES = frozenset(
    {
        LeaseState.USER_INTERVENED,
        LeaseState.UNLOCKED_DIRTY,
    }
)


OWNER_AUTHORIZABLE_STATES = frozenset(
    {
        LeaseState.LOCKED_IDLE,
        LeaseState.LOCKED_EDITING,
        LeaseState.LOCKED_RECOMPUTING,
        LeaseState.LOCKED_SAVING,
        LeaseState.LOCKED_ERROR,
    }
)


def bounded_text(value: str | None, limit: int) -> str:
    if not value:
        return ""
    clean = "".join(ch if ord(ch) >= 32 else " " for ch in str(value)).strip()
    return clean[:limit]


def bounded_diagnostic(
    value: str | None,
    limit: int,
    *,
    secrets_to_remove: Iterable[str] = (),
) -> str:
    """Bound display metadata after removing exact bearer credentials."""

    if not value:
        return ""
    clean = "".join(ch if ord(ch) >= 32 else " " for ch in str(value)).strip()
    for secret in (str(item) for item in secrets_to_remove):
        if not secret:
            continue
        clean = clean.replace(secret, "<redacted>")
        clean = clean.replace(token_fingerprint(secret), "<redacted>")
    return clean[:limit]
