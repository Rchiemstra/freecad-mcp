"""Native advisory guard for atomic sidecar publication."""

from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from ..sidecar_types.sidecar_lock_error import SidecarLockError
from ..sidecar_types.sidecar_permission_error import SidecarPermissionError
from .permissions import assert_windows_owner_only, harden_permissions

if TYPE_CHECKING:
    from ..sidecar_winapi.windows_overlapped import _WindowsOverlapped

_process_locks: dict[str, threading.RLock] = {}
_process_locks_guard = threading.Lock()


def process_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(os.path.abspath(str(path)))
    with _process_locks_guard:
        return _process_locks.setdefault(key, threading.RLock())


def open_guard(path: Path, *, strict_permissions: bool) -> int:
    path.parent.mkdir(parents=False, exist_ok=True)
    if path.is_symlink():
        raise SidecarLockError(f"guard path must not be a symlink: {path}")
    flags = os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    created = False
    try:
        try:
            fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
        except FileExistsError:
            # Open an existing guard without O_CREAT so a concurrent removal
            # cannot silently turn a permission-verification path into a new
            # file. The advisory lock is acquired immediately afterwards.
            fd = os.open(path, flags)
    except OSError as exc:
        raise SidecarLockError(f"unable to open sidecar guard {path}: {exc}") from exc
    try:
        if os.name == "nt" and strict_permissions and not created:
            assert_windows_owner_only(path, kind="guard file")
        else:
            harden_permissions(path, strict=strict_permissions)
    except SidecarPermissionError:
        os.close(fd)
        raise
    return fd


def lock_windows(fd: int) -> _WindowsOverlapped:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    from ..sidecar_winapi.windows_overlapped import _WindowsOverlapped

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    lock_file_ex = kernel32.LockFileEx
    lock_file_ex.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
    ]
    lock_file_ex.restype = wintypes.BOOL
    overlapped = _WindowsOverlapped()
    handle = msvcrt.get_osfhandle(fd)
    if not lock_file_ex(
        handle,
        0x00000002,  # LOCKFILE_EXCLUSIVE_LOCK; blocking, not fail-immediately
        0,
        0xFFFFFFFF,
        0xFFFFFFFF,
        ctypes.byref(overlapped.value),
    ):
        raise SidecarLockError(
            f"LockFileEx failed with Windows error {ctypes.get_last_error()}"
        )
    return overlapped


def unlock_windows(fd: int, overlapped: _WindowsOverlapped) -> None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    unlock_file_ex = kernel32.UnlockFileEx
    unlock_file_ex.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
    ]
    unlock_file_ex.restype = wintypes.BOOL
    if not unlock_file_ex(
        msvcrt.get_osfhandle(fd),
        0,
        0xFFFFFFFF,
        0xFFFFFFFF,
        ctypes.byref(overlapped.value),
    ):
        raise SidecarLockError(
            f"UnlockFileEx failed with Windows error {ctypes.get_last_error()}"
        )


@contextlib.contextmanager
def native_guard(path: Path, *, strict_permissions: bool = True) -> Iterator[None]:
    local_lock = process_lock(path)
    with local_lock:
        fd = open_guard(path, strict_permissions=strict_permissions)
        windows_lock: _WindowsOverlapped | None = None
        locked_posix = False
        try:
            if os.name == "nt":
                windows_lock = lock_windows(fd)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX)
                locked_posix = True
            yield
        finally:
            try:
                if windows_lock is not None:
                    unlock_windows(fd, windows_lock)
                elif locked_posix:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
