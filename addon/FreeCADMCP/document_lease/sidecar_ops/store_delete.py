"""Atomic sidecar deletion under a native guard."""

from __future__ import annotations

from pathlib import Path

from ..model import LeaseRecord
from ..sidecar_types.sidecar_error import SidecarError

_LEGACY_MESSAGE = (
    "LEGACY_LEASE_AUTHORITY_REMOVED: Document authority is owned by native "
    "FreeCAD collaboration."
)


def delete_sidecar(
    sidecar: Path,
    *,
    expected: LeaseRecord,
    max_bytes: int,
    strict_permissions: bool,
) -> None:
    del sidecar, expected, max_bytes, strict_permissions
    raise SidecarError(_LEGACY_MESSAGE)
