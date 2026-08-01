"""Owner-only permission hardening for sidecar artifacts."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from ..sidecar_types.sidecar_permission_error import SidecarPermissionError
from .windows_dacl_inspect import inspect_windows_owner_only
from .windows_dacl_set import set_windows_owner_only


def assert_windows_owner_only(path: Path, *, kind: str) -> None:
    valid, reason = inspect_windows_owner_only(path)
    if not valid:
        raise SidecarPermissionError(
            f"{kind} does not have the required protected owner-only Windows DACL: "
            f"{path} ({reason})"
        )


def harden_owner_only(
    path: str | os.PathLike[str],
    *,
    mode: int,
    strict: bool,
    kind: str,
) -> None:
    target = Path(path)
    try:
        os.chmod(target, mode)
    except OSError as exc:
        if strict:
            raise SidecarPermissionError(
                f"unable to set owner-only permissions on {kind} {target}: {exc}"
            ) from exc
    if os.name == "nt":
        if not set_windows_owner_only(target) and strict:
            raise SidecarPermissionError(
                f"unable to apply an owner-only Windows DACL to {kind} {target}"
            )
        if strict:
            assert_windows_owner_only(target, kind=kind)
        return
    try:
        actual_mode = stat.S_IMODE(target.stat().st_mode)
    except OSError as exc:
        if strict:
            raise SidecarPermissionError(
                f"unable to inspect {kind} {target}: {exc}"
            ) from exc
        return
    if actual_mode != mode and strict:
        raise SidecarPermissionError(
            f"{kind} permissions are not owner-only {mode:o}: {target}"
        )


def harden_permissions(
    path: str | os.PathLike[str], *, strict: bool
) -> None:
    """Apply owner-only ``0600`` permissions to a file artifact."""

    harden_owner_only(
        path,
        mode=0o600,
        strict=strict,
        kind="file",
    )


def harden_directory_permissions(
    path: str | os.PathLike[str], *, strict: bool
) -> None:
    """Apply traversable owner-only ``0700`` permissions to a directory."""

    target = Path(path)
    try:
        is_directory = target.is_dir()
    except OSError as exc:
        if strict:
            raise SidecarPermissionError(
                f"unable to inspect directory {target}: {exc}"
            ) from exc
        return
    if not is_directory:
        if strict:
            raise SidecarPermissionError(
                f"owner-only directory target is not a directory: {target}"
            )
        return
    harden_owner_only(
        target,
        mode=0o700,
        strict=strict,
        kind="directory",
    )
