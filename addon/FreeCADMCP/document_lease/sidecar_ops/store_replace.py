"""Atomic sidecar replacement under a native guard."""

from __future__ import annotations

from pathlib import Path

from ..model import LeaseRecord
from ..sidecar_types.sidecar_error import SidecarError

_LEGACY_MESSAGE = (
    "LEGACY_LEASE_AUTHORITY_REMOVED: Document authority is owned by native "
    "FreeCAD collaboration."
)


def replace_sidecar(
    sidecar: Path,
    record: LeaseRecord,
    *,
    expected: LeaseRecord,
    max_bytes: int,
    strict_permissions: bool,
    persist_task_summary: bool,
) -> None:
    del (
        sidecar,
        record,
        expected,
        max_bytes,
        strict_permissions,
        persist_task_summary,
    )
    raise SidecarError(_LEGACY_MESSAGE)
