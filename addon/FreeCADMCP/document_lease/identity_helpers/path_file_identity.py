"""Filesystem identity probes for document paths."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ..model import FileIdentity
from .path_canonicalize import canonicalize_path
from .platform import platform_name

if TYPE_CHECKING:
    from os import PathLike


def windows_file_identity(path: str) -> FileIdentity | None:
    """Read volume/file-index identity using a handle, when running on Windows."""

    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        from ..identity_types.by_handle_file_information import BY_HANDLE_FILE_INFORMATION

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.restype = wintypes.HANDLE
        create_file.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        handle = create_file(
            path,
            0x80,  # FILE_READ_ATTRIBUTES
            0x1 | 0x2 | 0x4,  # FILE_SHARE_READ/WRITE/DELETE
            None,
            3,  # OPEN_EXISTING
            0x02000000,  # FILE_FLAG_BACKUP_SEMANTICS
            None,
        )
        invalid = wintypes.HANDLE(-1).value
        if handle == invalid:
            return None
        try:
            info = BY_HANDLE_FILE_INFORMATION()
            if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
                return None
            file_index = (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow)
            return FileIdentity(
                platform="windows",
                volume_serial=int(info.dwVolumeSerialNumber),
                file_index=file_index,
            )
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, ValueError):
        return None


def file_identity_for_path(
    path: str | PathLike[str], *, platform: str | None = None
) -> FileIdentity | None:
    """Return a best-effort filesystem identity for an existing regular file."""

    canonical, _ = canonicalize_path(path, platform=platform)
    if not os.path.exists(canonical):
        return None
    target = platform_name(platform)
    if target == "windows" and os.name == "nt":
        result = windows_file_identity(canonical)
        if result is not None:
            return result
    try:
        stat_result = os.stat(canonical, follow_symlinks=True)
    except OSError:
        return None
    if target == "windows":
        # Python exposes stable st_dev/st_ino on current Windows versions.  Map
        # them onto the Windows wire shape when the Win32 handle path failed.
        return FileIdentity(
            platform="windows",
            volume_serial=int(stat_result.st_dev),
            file_index=int(stat_result.st_ino),
        )
    return FileIdentity(
        platform="posix",
        device=int(stat_result.st_dev),
        inode=int(stat_result.st_ino),
    )
