"""Atomic sidecar deletion under a native guard."""

from __future__ import annotations

import contextlib
from pathlib import Path

from .. import sidecar as sidecar_mod
from ..model import LeaseRecord
from ..sidecar_types.sidecar_commit_uncertain_error import SidecarCommitUncertainError
from ..sidecar_types.sidecar_conflict_error import SidecarConflictError
from ..sidecar_types.sidecar_error import SidecarError
from .cas import matches_cas
from .guard import native_guard
from .paths import guard_path_for


def delete_sidecar(
    sidecar: Path,
    *,
    expected: LeaseRecord,
    max_bytes: int,
    strict_permissions: bool,
) -> None:
    with native_guard(
        guard_path_for(sidecar), strict_permissions=strict_permissions
    ):
        current = sidecar_mod._read_record(
            sidecar,
            max_bytes=max_bytes,
            strict_permissions=strict_permissions,
        )
        if not matches_cas(current, expected):
            raise SidecarConflictError("sidecar changed before deletion")
        deleted = False
        try:
            sidecar.unlink()
            deleted = True
            sidecar_mod._fsync_directory(sidecar.parent)
        except FileNotFoundError:
            raise SidecarConflictError("sidecar disappeared before deletion") from None
        except OSError as exc:
            if deleted:
                persisted = None
                absent = not sidecar_mod.os.path.lexists(sidecar)
                if not absent:
                    with contextlib.suppress(SidecarError):
                        persisted = sidecar_mod._read_record(
                            sidecar,
                            max_bytes=max_bytes,
                            strict_permissions=strict_permissions,
                        )
                raise SidecarCommitUncertainError(
                    "sidecar deletion was published but its "
                    "post-publication checks failed",
                    persisted=persisted,
                    absent=absent,
                ) from exc
            raise SidecarError(f"unable to delete sidecar {sidecar}: {exc}") from exc
