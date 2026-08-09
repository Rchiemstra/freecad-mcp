"""Frozen compatibility adapter for the removed lease-enforced GUI path."""

from __future__ import annotations

from typing import Any


def _legacy_lease_authority_removed() -> dict[str, Any]:
    return {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": "Document authority is owned by native FreeCAD collaboration.",
    }


def run_enforced_lease_service_task(
    self,
    collaborators,
    original_task,
    captured,
    inflight,
    *,
    completion_lock,
    completion_handoff,
):
    """Return the frozen result for the retired lease-enforced GUI dispatcher."""

    del (
        self,
        collaborators,
        original_task,
        captured,
        inflight,
        completion_lock,
        completion_handoff,
    )
    return _legacy_lease_authority_removed()
