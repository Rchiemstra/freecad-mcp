"""Stable, no-follow launch sources for trusted Python scripts.

The name used to approve a script must remain the name used at process
creation.  Windows makes that possible by keeping a deny-write/delete handle
open; POSIX uses the opened descriptor as the script object so a rename cannot
change what the interpreter reads.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import subprocess
from typing import Callable, Mapping, Sequence

from .validation import ValidationIssue


class LaunchSourceError(ValueError):
    """A stable structured rejection which callers may preserve verbatim."""

    def __init__(self, stage: str, code: str, artifact: str, field: str) -> None:
        self.issue = ValidationIssue(stage, code, artifact, field)
        super().__init__(f"{stage}:{code}:{artifact}:{field}")


@dataclass
class ApprovedLaunchSource:
    path: Path
    expected_sha256: str
    stage: str
    artifact: str
    code_prefix: str
    before_open_hook: Callable[[], None] | None = None
    _fd: int | None = None
    _identity: tuple[int, int, int, int] | None = None

    def __enter__(self) -> "ApprovedLaunchSource":
        self.path = self.path.absolute()
        self._reject_reparse_ancestors()
        try:
            # Test-only deterministic race hooks are injected by a signed
            # packet runner.  Normal production construction leaves this None.
            if self.before_open_hook is not None:
                self.before_open_hook()
            self._fd = _open_regular_nofollow(self.path)
            # An ancestor can become a junction between the first walk and
            # CreateFileW.  Reject it even when the opened leaf itself is
            # regular, before hashing or allowing a spawn.
            self._reject_reparse_ancestors()
            if not _final_handle_matches(self._fd, self.path):
                raise self._error("REPARSE", "/final_path")
            before = os.fstat(self._fd)
            if not stat.S_ISREG(before.st_mode):
                raise OSError("not a regular file")
            digest = _hash_open_descriptor(self._fd)
            after = os.fstat(self._fd)
        except LaunchSourceError:
            self.close()
            raise
        except OSError as error:
            self.close()
            raise self._error("UNAVAILABLE", "/path") from error
        self._identity = _identity(before)
        if self._identity != _identity(after):
            self.close()
            raise self._error("CHANGED", "/path")
        if digest != self.expected_sha256:
            self.close()
            raise self._error("HASH", "/sha256")
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    @property
    def launch_path(self) -> str:
        if self._fd is None:
            raise RuntimeError("launch source is closed")
        # Windows keeps the exact checked pathname locked against write/delete.
        # POSIX executes a descriptor name, never a subsequently reopened path.
        if os.name == "nt":
            return str(self.path)
        for root in ("/proc/self/fd", "/dev/fd"):
            if os.path.isdir(root):
                return f"{root}/{self._fd}"
        raise self._error("UNAVAILABLE", "/descriptor")

    def run(
        self,
        command: Sequence[str],
        script_index: int,
        extra: Sequence[str],
        *,
        environment: Mapping[str, str],
        timeout: float,
        before_spawn: Callable[[], None] | None = None,
        additional_sources: Mapping[int, "ApprovedLaunchSource"] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if self._fd is None:
            raise RuntimeError("launch source is closed")
        if before_spawn is not None:
            before_spawn()
        # This detects a POSIX rename after the hook.  Windows rejects that
        # rename while the handle is held, and still runs the same pathname.
        sources = {script_index: self, **(additional_sources or {})}
        for source in sources.values():
            source._verify_live_name()
        argv = list(command)
        # POSIX `executable` selects the held interpreter descriptor while
        # retaining argv[0] as the signed selected pathname.  Rewriting it to
        # /proc/self/fd would make the bootstrap bind a different command.
        # The governed script is still always fd-backed.
        if os.name == "nt":
            for index, source in sources.items():
                argv[index] = source.launch_path
        else:
            argv[script_index] = self.launch_path
        argv.extend(extra)
        kwargs: dict[str, object] = {
            "capture_output": True,
            "text": True,
            "check": False,
            "env": dict(environment),
            "timeout": timeout,
        }
        if os.name != "nt":
            kwargs["pass_fds"] = tuple(source._fd for source in sources.values() if source._fd is not None)
            interpreter = (additional_sources or {}).get(0)
            if interpreter is not None:
                kwargs["executable"] = interpreter.launch_path
        return subprocess.run(argv, **kwargs)  # type: ignore[arg-type]

    def _reject_reparse_ancestors(self) -> None:
        current = Path(self.path.anchor)
        for part in self.path.parts[1:]:
            current /= part
            try:
                details = os.lstat(current)
            except OSError as error:
                raise self._error("UNAVAILABLE", "/ancestors") from error
            attributes = getattr(details, "st_file_attributes", 0)
            if stat.S_ISLNK(details.st_mode) or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise self._error("REPARSE", "/ancestors")

    def _verify_live_name(self) -> None:
        try:
            self._reject_reparse_ancestors()
            live = os.stat(self.path, follow_symlinks=False)
        except OSError as error:
            raise self._error("CHANGED", "/path") from error
        if self._identity != _identity(live):
            raise self._error("CHANGED", "/path")

    def _error(self, suffix: str, field: str) -> LaunchSourceError:
        return LaunchSourceError(self.stage, f"{self.code_prefix}_{suffix}", self.artifact, field)


def _identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (value.st_dev, value.st_ino, value.st_size, getattr(value, "st_mtime_ns", 0))


def _hash_open_descriptor(descriptor: int) -> str:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while True:
        data = os.read(descriptor, 1024 * 1024)
        if not data:
            break
        digest.update(data)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest()


def _open_regular_nofollow(path: Path) -> int:
    if os.name != "nt":
        return os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    import ctypes
    import msvcrt

    GENERIC_READ = 0x80000000
    FILE_SHARE_READ = 0x00000001
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x00000080
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    # FILE_SHARE_READ permits the interpreter to read the same script but
    # withholds FILE_SHARE_WRITE and FILE_SHARE_DELETE until process creation.
    handle = kernel.CreateFileW(
        str(path), GENERIC_READ, FILE_SHARE_READ, None, OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle in (None, invalid):
        raise OSError(ctypes.get_last_error(), "CreateFileW")
    try:
        class _AttributeTag(ctypes.Structure):
            _fields_ = [("attributes", ctypes.c_ulong), ("reparse_tag", ctypes.c_ulong)]
        attributes = _AttributeTag()
        if not kernel.GetFileInformationByHandleEx(ctypes.c_void_p(handle), 9, ctypes.byref(attributes), ctypes.sizeof(attributes)):
            raise OSError(ctypes.get_last_error(), "GetFileInformationByHandleEx")
        if attributes.attributes & 0x400:
            raise OSError("reparse point")
        return msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        kernel.CloseHandle(ctypes.c_void_p(handle))
        raise


def _final_handle_matches(descriptor: int, path: Path) -> bool:
    """Confirm a Windows handle did not traverse a raced ancestor junction."""
    if os.name != "nt":
        return True
    import ctypes
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetFinalPathNameByHandleW.restype = ctypes.c_ulong
    kernel.GetFinalPathNameByHandleW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong]
    required = kernel.GetFinalPathNameByHandleW(ctypes.c_void_p(msvcrt.get_osfhandle(descriptor)), None, 0, 0)
    if not required:
        raise OSError(ctypes.get_last_error(), "GetFinalPathNameByHandleW")
    buffer = ctypes.create_unicode_buffer(required + 1)
    written = kernel.GetFinalPathNameByHandleW(ctypes.c_void_p(msvcrt.get_osfhandle(descriptor)), buffer, len(buffer), 0)
    if not written or written >= len(buffer):
        raise OSError(ctypes.get_last_error(), "GetFinalPathNameByHandleW")
    def normalized(value: str) -> str:
        return os.path.normcase(os.path.normpath(value.removeprefix("\\\\?\\")))
    return normalized(buffer.value) == normalized(str(path))
