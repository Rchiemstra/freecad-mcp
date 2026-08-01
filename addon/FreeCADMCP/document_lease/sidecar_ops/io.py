"""Read and write sidecar files on disk."""

from __future__ import annotations

import contextlib
import os
import stat
import tempfile
from pathlib import Path

from .. import sidecar as sidecar_mod
from ..model import LeaseRecord
from ..sidecar_types.sidecar_error import SidecarError
from ..sidecar_types.sidecar_malformed_error import SidecarMalformedError
from ..sidecar_types.sidecar_not_found_error import SidecarNotFoundError
from ..sidecar_types.sidecar_permission_error import SidecarPermissionError
from .codec import parse_sidecar_bytes
from .permissions import assert_windows_owner_only, harden_permissions


def assert_regular_not_symlink(
    path: Path, *, strict_permissions: bool
) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise SidecarNotFoundError(str(path)) from None
    except OSError as exc:
        raise SidecarError(f"unable to inspect sidecar {path}: {exc}") from exc
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    if stat.S_ISLNK(info.st_mode) or file_attributes & reparse_flag:
        raise SidecarMalformedError(
            f"sidecar must not be a symlink or reparse point: {path}"
        )
    if not stat.S_ISREG(info.st_mode):
        raise SidecarMalformedError(f"sidecar must be a regular file: {path}")
    if strict_permissions and sidecar_mod.os.name != "nt":
        mode = stat.S_IMODE(info.st_mode)
        if mode != 0o600:
            raise SidecarPermissionError(
                f"sidecar permissions must be exactly owner-only 0600: {path}"
            )
    elif strict_permissions:
        assert_windows_owner_only(path, kind="sidecar file")


def read_record(
    path: Path, *, max_bytes: int, strict_permissions: bool
) -> LeaseRecord:
    assert_regular_not_symlink(
        path, strict_permissions=strict_permissions
    )
    try:
        with path.open("rb") as handle:
            data = handle.read(max_bytes + 1)
    except FileNotFoundError:
        raise SidecarNotFoundError(str(path)) from None
    except OSError as exc:
        raise SidecarError(f"unable to read sidecar {path}: {exc}") from exc
    return parse_sidecar_bytes(data, max_bytes=max_bytes)


def write_temp(
    path: Path, payload: bytes, *, strict_permissions: bool
) -> Path:
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=path.parent
        )
    except OSError as exc:
        raise SidecarError(f"unable to create a sidecar temporary file: {exc}") from exc
    temp_path = Path(temp_name)
    try:
        harden_permissions(temp_path, strict=strict_permissions)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return temp_path
    except Exception:
        if fd >= 0:
            os.close(fd)
        with contextlib.suppress(OSError):
            temp_path.unlink()
        raise
