"""Atomic sidecar replacement under a native guard."""

from __future__ import annotations

import contextlib
from pathlib import Path

from .. import sidecar as sidecar_mod
from ..model import LeaseRecord
from ..sidecar_types.sidecar_commit_uncertain_error import SidecarCommitUncertainError
from ..sidecar_types.sidecar_conflict_error import SidecarConflictError
from ..sidecar_types.sidecar_error import SidecarError
from .cas import matches_cas
from .codec import serialize_record
from .guard import native_guard
from .io import write_temp
from .paths import guard_path_for
from .permissions import harden_permissions


def replace_sidecar(
    sidecar: Path,
    record: LeaseRecord,
    *,
    expected: LeaseRecord,
    max_bytes: int,
    strict_permissions: bool,
    persist_task_summary: bool,
) -> None:
    if record.record_revision != expected.record_revision + 1:
        raise SidecarConflictError(
            "replacement record_revision must be exactly one greater than expected"
        )
    payload = serialize_record(
        record,
        max_bytes=max_bytes,
        persist_task_summary=persist_task_summary,
    )
    with native_guard(
        guard_path_for(sidecar), strict_permissions=strict_permissions
    ):
        current = sidecar_mod._read_record(
            sidecar,
            max_bytes=max_bytes,
            strict_permissions=strict_permissions,
        )
        if not matches_cas(current, expected):
            raise SidecarConflictError("sidecar changed before replacement")
        temporary = write_temp(
            sidecar, payload, strict_permissions=strict_permissions
        )
        published = False
        try:
            sidecar_mod.os.replace(temporary, sidecar)
            published = True
            harden_permissions(sidecar, strict=strict_permissions)
            sidecar_mod._fsync_directory(sidecar.parent)
        except Exception as exc:
            persisted = None
            if published:
                with contextlib.suppress(SidecarError):
                    # Inspect while the native CAS guard is still held.
                    persisted = sidecar_mod._read_record(
                        sidecar,
                        max_bytes=max_bytes,
                        strict_permissions=strict_permissions,
                    )
            with contextlib.suppress(OSError):
                temporary.unlink()
            if published:
                raise SidecarCommitUncertainError(
                    "sidecar replacement was published but its "
                    "post-publication checks failed",
                    persisted=persisted,
                ) from exc
            if isinstance(exc, SidecarError):
                raise
            if isinstance(exc, OSError):
                raise SidecarError(
                    f"unable to replace sidecar {sidecar}: {exc}"
                ) from exc
            raise
