"""Frozen compatibility adapter for the removed document lease service.

Native FreeCAD collaboration owns document authority after the Phase 18
cutover.  The historic constructor remains callable so old imports receive a
deterministic deprecation result instead of failing during import or lookup.
"""

from __future__ import annotations

import secrets
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

__all__ = ("DocumentLeaseService",)


def _legacy_lease_authority_removed() -> dict[str, object]:
    """Return a fresh result for the removed legacy authority."""

    return {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": "Document authority is owned by native FreeCAD collaboration.",
    }


def utc_now() -> str:
    """Retain the historic pure clock default without importing lease state."""

    return datetime.now(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def DocumentLeaseService(
    identity_service: DocumentIdentityService,  # noqa: F821
    sidecar_store: SidecarStore | None = None,  # noqa: F821
    *,
    token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    uuid_factory: Callable[[], uuid.UUID | str] = uuid.uuid4,
    utc_clock: Callable[[], str] = utc_now,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    sidecar_heartbeat_interval_seconds: float = 30.0,
    stale_after_seconds: float = 90.0,
    local_runtime_identity: LocalRuntimeIdentity | None = None,  # noqa: F821
    process_liveness_probe: (
        Callable[[int], ProcessLivenessEvidence] | None  # noqa: F821
    ) = None,
) -> dict[str, object]:
    """Retain the historic constructor surface as a deprecation callable."""

    del (
        identity_service,
        sidecar_store,
        token_factory,
        uuid_factory,
        utc_clock,
        monotonic_ns,
        sidecar_heartbeat_interval_seconds,
        stale_after_seconds,
        local_runtime_identity,
        process_liveness_probe,
    )
    return _legacy_lease_authority_removed()
