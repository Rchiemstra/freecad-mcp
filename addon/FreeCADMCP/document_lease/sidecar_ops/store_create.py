"""Atomic sidecar creation under a native guard."""

from __future__ import annotations

import contextlib
import errno
from pathlib import Path

from .. import sidecar as sidecar_mod
from ..model import LeaseRecord
from ..sidecar_types.sidecar_atomicity_error import SidecarAtomicityError
from ..sidecar_types.sidecar_commit_uncertain_error import SidecarCommitUncertainError
from ..sidecar_types.sidecar_error import SidecarError
from ..sidecar_types.sidecar_exists_error import SidecarExistsError
from .codec import serialize_record
from .guard import native_guard
from .io import write_temp
from .paths import guard_path_for
from .permissions import harden_permissions


def create_sidecar(
    sidecar: Path,
    record: LeaseRecord,
    *,
    max_bytes: int,
    strict_permissions: bool,
    persist_task_summary: bool,
) -> None:
    payload = serialize_record(
        record,
        max_bytes=max_bytes,
        persist_task_summary=persist_task_summary,
    )
    with native_guard(
        guard_path_for(sidecar), strict_permissions=strict_permissions
    ):
        if sidecar_mod.os.path.lexists(sidecar):
            # Do not parse/delete here: malformed and stale records are still
            # conflicts that need an explicit recovery workflow.
            raise SidecarExistsError(str(sidecar))
        temporary = write_temp(
            sidecar, payload, strict_permissions=strict_permissions
        )
        published = False
        try:
            try:
                sidecar_mod.os.link(temporary, sidecar)
                published = True
            except FileExistsError:
                raise SidecarExistsError(str(sidecar)) from None
            except OSError as exc:
                if exc.errno in {
                    errno.EPERM,
                    errno.ENOTSUP,
                    getattr(errno, "EOPNOTSUPP", errno.ENOTSUP),
                }:
                    raise SidecarAtomicityError(
                        "filesystem does not support atomic no-replace sidecar publication"
                    ) from exc
                raise
            harden_permissions(sidecar, strict=strict_permissions)
            sidecar_mod._fsync_directory(sidecar.parent)
        except Exception as exc:
            persisted = None
            if published:
                with contextlib.suppress(SidecarError):
                    # Inspect while the native no-replace guard is still
                    # held, exactly as replacement does.
                    persisted = sidecar_mod._read_record(
                        sidecar,
                        max_bytes=max_bytes,
                        strict_permissions=strict_permissions,
                    )
                raise SidecarCommitUncertainError(
                    "sidecar creation was published but its "
                    "post-publication checks failed",
                    persisted=persisted,
                    absent=False,
                ) from exc
            if isinstance(exc, SidecarError):
                raise
            if isinstance(exc, OSError):
                raise SidecarError(
                    f"unable to create sidecar {sidecar}: {exc}"
                ) from exc
            raise
        finally:
            with contextlib.suppress(OSError):
                temporary.unlink()
