"""Frozen compatibility adapter for removed MCP stale-lease recovery."""

from __future__ import annotations

__all__ = ("StaleLeaseRecoveryOrchestrator",)


def _legacy_lease_authority_removed() -> dict[str, object]:
    """Return a fresh, deterministic result for the removed authority."""

    return {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": "Document authority is owned by native FreeCAD collaboration.",
    }


def StaleLeaseRecoveryOrchestrator(
    *,
    stale_after_seconds=90.0,
    blocking_timeout_s=120.0,
) -> dict[str, object]:
    """Retain the historic constructor surface as a deprecation callable."""

    del stale_after_seconds, blocking_timeout_s
    return _legacy_lease_authority_removed()
