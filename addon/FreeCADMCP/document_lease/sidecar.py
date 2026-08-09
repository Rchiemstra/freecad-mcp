"""Guarded, schema-validated persistence for adjacent lease sidecars."""

from __future__ import annotations

import contextlib
import errno
import json
import os
import stat
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from uuid import UUID

from .model import (
    RECORD_KIND,
    SCHEMA_VERSION,
    TOKEN_FINGERPRINT_RE,
    LeaseRecord,
    LeaseState,
)


MAX_SIDECAR_BYTES = 64 * 1024
SIDECAR_SUFFIX = ".freecad-mcp.lock"
GUARD_SUFFIX = ".guard"


class SidecarError(RuntimeError):
    pass


class SidecarNotFoundError(SidecarError):
    pass


class SidecarExistsError(SidecarError):
    pass


class SidecarMalformedError(SidecarError):
    pass


class SidecarTooLargeError(SidecarMalformedError):
    pass


class SidecarConflictError(SidecarError):
    pass


class SidecarPermissionError(SidecarError):
    pass


class SidecarLockError(SidecarError):
    pass


class SidecarAtomicityError(SidecarError):
    pass


class SidecarNetworkPathError(SidecarError):
    pass


def sidecar_path_for(document_path: str | os.PathLike[str]) -> Path:
    return Path(os.fspath(document_path) + SIDECAR_SUFFIX)


def guard_path_for(sidecar_path: str | os.PathLike[str]) -> Path:
    return Path(os.fspath(sidecar_path) + GUARD_SUFFIX)


def _is_network_path(path: Path) -> bool:
    value = str(path)
    if value.startswith("\\\\") or value.startswith("//"):
        return True
    if os.name == "nt":
        # UNC checks do not catch mapped network drives. Query the resolved
        # drive root without touching the target file; DRIVE_REMOTE is 4.
        try:
            import ctypes

            absolute = os.path.abspath(value)
            drive, _tail = os.path.splitdrive(absolute)
            if drive:
                root = drive + "\\"
                return int(ctypes.windll.kernel32.GetDriveTypeW(root)) == 4
        except (AttributeError, OSError, ValueError):
            # Detection uncertainty is handled by the caller's other
            # fail-closed filesystem/permission checks.
            pass
    elif os.path.isfile("/proc/self/mountinfo"):
        # Linux exposes the filesystem type after the " - " separator. Use
        # the longest matching mount point so a local parent mount cannot mask
        # an NFS/CIFS/SSHFS child mount.
        network_types = {
            "9p",
            "afs",
            "ceph",
            "cifs",
            "fuse.sshfs",
            "ncpfs",
            "nfs",
            "nfs4",
            "smb3",
        }
        try:
            target = os.path.realpath(os.path.abspath(value))
            matches: list[tuple[int, str]] = []
            with open("/proc/self/mountinfo", encoding="utf-8") as mounts:
                for line in mounts:
                    left, separator, right = line.rstrip("\n").partition(" - ")
                    if not separator:
                        continue
                    fields = left.split()
                    filesystem = right.split(maxsplit=1)[0]
                    if len(fields) < 5:
                        continue
                    mount_point = (
                        fields[4]
                        .replace("\\040", " ")
                        .replace("\\011", "\t")
                        .replace("\\134", "\\")
                    )
                    if target == mount_point or target.startswith(
                        mount_point.rstrip(os.sep) + os.sep
                    ):
                        matches.append((len(mount_point), filesystem))
            if matches:
                return max(matches)[1].lower() in network_types
        except (OSError, ValueError):
            pass
    return False


_process_locks: dict[str, threading.RLock] = {}
_process_locks_guard = threading.Lock()


def _process_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(os.path.abspath(str(path)))
    with _process_locks_guard:
        return _process_locks.setdefault(key, threading.RLock())


def _open_guard(path: Path, *, strict_permissions: bool) -> int:
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
            _assert_windows_owner_only(path, kind="guard file")
        else:
            _harden_permissions(path, strict=strict_permissions)
    except SidecarPermissionError:
        os.close(fd)
        raise
    return fd


class _WindowsOverlapped:
    """Lazy ctypes OVERLAPPED holder, kept alive for LockFileEx."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class _OVERLAPPED(ctypes.Structure):
            _fields_ = [
                # ctypes.wintypes does not expose ULONG_PTR on every Python
                # distribution; c_size_t is the ABI-equivalent pointer-sized
                # unsigned value used by OVERLAPPED.
                ("Internal", ctypes.c_size_t),
                ("InternalHigh", ctypes.c_size_t),
                ("Offset", wintypes.DWORD),
                ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE),
            ]

        self.value = _OVERLAPPED()


def _lock_windows(fd: int) -> _WindowsOverlapped:
    import ctypes
    import msvcrt
    from ctypes import wintypes

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


def _unlock_windows(fd: int, overlapped: _WindowsOverlapped) -> None:
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
def _native_guard(path: Path, *, strict_permissions: bool = True) -> Iterator[None]:
    local_lock = _process_lock(path)
    with local_lock:
        fd = _open_guard(path, strict_permissions=strict_permissions)
        windows_lock: _WindowsOverlapped | None = None
        locked_posix = False
        try:
            if os.name == "nt":
                windows_lock = _lock_windows(fd)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX)
                locked_posix = True
            yield
        finally:
            try:
                if windows_lock is not None:
                    _unlock_windows(fd, windows_lock)
                elif locked_posix:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


def _set_windows_owner_only(path: Path) -> bool:
    """Apply a protected owner/system-only DACL with native APIs.

    This code is deliberately best-effort because non-NT filesystems may not
    support ACLs.  Enforce callers choose whether failure is fatal.
    """

    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        descriptor = wintypes.LPVOID()
        convert_descriptor = (
            advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
        )
        convert_descriptor.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.ULONG),
        ]
        convert_descriptor.restype = wintypes.BOOL
        get_dacl = advapi32.GetSecurityDescriptorDacl
        get_dacl.argtypes = [
            wintypes.LPVOID,
            ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.BOOL),
        ]
        get_dacl.restype = wintypes.BOOL
        set_security = advapi32.SetNamedSecurityInfoW
        set_security.argtypes = [
            wintypes.LPWSTR,
            ctypes.c_int,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.LPVOID,
        ]
        set_security.restype = wintypes.DWORD
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        # Protected DACL; full access for SYSTEM and the object's owner-rights
        # SID.  The file is created by the current user, who is its owner.
        sddl = "D:P(A;;FA;;;SY)(A;;FA;;;OW)"
        if not convert_descriptor(
            sddl, 1, ctypes.byref(descriptor), None
        ):
            return False
        try:
            dacl_present = wintypes.BOOL()
            dacl_defaulted = wintypes.BOOL()
            dacl = wintypes.LPVOID()
            if not get_dacl(
                descriptor,
                ctypes.byref(dacl_present),
                ctypes.byref(dacl),
                ctypes.byref(dacl_defaulted),
            ):
                return False
            result = set_security(
                str(path),
                1,  # SE_FILE_OBJECT
                0x00000004 | 0x80000000,  # DACL + PROTECTED_DACL
                None,
                None,
                dacl,
                None,
            )
            return result == 0
        finally:
            kernel32.LocalFree(descriptor)
    except (AttributeError, OSError, ValueError):
        return False


def _inspect_windows_owner_only(path: Path) -> tuple[bool, str]:
    """Inspect an NT security descriptor without modifying it.

    The writer installs ``D:P(A;;FA;;;SY)(A;;FA;;;OW)``.  A strict reader
    accepts only that effective structure on an object owned by the current
    process user: a protected DACL with exactly two non-inherited allow ACEs,
    both granting ``FILE_ALL_ACCESS``, to SYSTEM and OWNER RIGHTS.  Checking
    the ACEs directly avoids brittle SDDL string comparison and rejects extra
    allow/deny/object/inherited ACEs.
    """

    if os.name != "nt":
        return True, ""

    try:
        import ctypes
        from ctypes import wintypes

        class _AclSizeInformation(ctypes.Structure):
            _fields_ = [
                ("AceCount", wintypes.DWORD),
                ("AclBytesInUse", wintypes.DWORD),
                ("AclBytesFree", wintypes.DWORD),
            ]

        class _AceHeader(ctypes.Structure):
            _fields_ = [
                ("AceType", wintypes.BYTE),
                ("AceFlags", wintypes.BYTE),
                ("AceSize", wintypes.WORD),
            ]

        class _AccessAllowedAce(ctypes.Structure):
            _fields_ = [
                ("Header", _AceHeader),
                ("Mask", wintypes.DWORD),
                ("SidStart", wintypes.DWORD),
            ]

        class _SidAndAttributes(ctypes.Structure):
            _fields_ = [
                ("Sid", wintypes.LPVOID),
                ("Attributes", wintypes.DWORD),
            ]

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        get_named_security = advapi32.GetNamedSecurityInfoW
        get_named_security.argtypes = [
            wintypes.LPWSTR,
            ctypes.c_int,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID),
        ]
        get_named_security.restype = wintypes.DWORD

        get_descriptor_control = advapi32.GetSecurityDescriptorControl
        get_descriptor_control.argtypes = [
            wintypes.LPVOID,
            ctypes.POINTER(ctypes.c_ushort),
            ctypes.POINTER(wintypes.DWORD),
        ]
        get_descriptor_control.restype = wintypes.BOOL

        get_acl_information = advapi32.GetAclInformation
        get_acl_information.argtypes = [
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.c_int,
        ]
        get_acl_information.restype = wintypes.BOOL

        get_ace = advapi32.GetAce
        get_ace.argtypes = [
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.LPVOID),
        ]
        get_ace.restype = wintypes.BOOL

        equal_sid = advapi32.EqualSid
        equal_sid.argtypes = [wintypes.LPVOID, wintypes.LPVOID]
        equal_sid.restype = wintypes.BOOL
        is_valid_sid = advapi32.IsValidSid
        is_valid_sid.argtypes = [wintypes.LPVOID]
        is_valid_sid.restype = wintypes.BOOL
        get_length_sid = advapi32.GetLengthSid
        get_length_sid.argtypes = [wintypes.LPVOID]
        get_length_sid.restype = wintypes.DWORD

        convert_sid = advapi32.ConvertStringSidToSidW
        convert_sid.argtypes = [
            wintypes.LPCWSTR,
            ctypes.POINTER(wintypes.LPVOID),
        ]
        convert_sid.restype = wintypes.BOOL

        open_process_token = advapi32.OpenProcessToken
        open_process_token.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        open_process_token.restype = wintypes.BOOL
        get_token_information = advapi32.GetTokenInformation
        get_token_information.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        get_token_information.restype = wintypes.BOOL

        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL

        owner = wintypes.LPVOID()
        dacl = wintypes.LPVOID()
        descriptor = wintypes.LPVOID()
        security_result = get_named_security(
            str(path),
            1,  # SE_FILE_OBJECT
            0x00000001 | 0x00000004,  # OWNER + DACL_SECURITY_INFORMATION
            ctypes.byref(owner),
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
        if security_result != 0:
            return False, f"GetNamedSecurityInfoW failed with error {security_result}"

        token = wintypes.HANDLE()
        expected_sids: list[wintypes.LPVOID] = []
        try:
            if not owner.value:
                return False, "security descriptor has no owner SID"
            if not dacl.value:
                return False, "security descriptor has a null or absent DACL"

            control = ctypes.c_ushort()
            revision = wintypes.DWORD()
            if not get_descriptor_control(
                descriptor, ctypes.byref(control), ctypes.byref(revision)
            ):
                return False, (
                    "GetSecurityDescriptorControl failed with Windows error "
                    f"{ctypes.get_last_error()}"
                )
            if not control.value & 0x1000:  # SE_DACL_PROTECTED
                return False, "DACL is not protected from inheritance"

            if not open_process_token(
                kernel32.GetCurrentProcess(),
                0x0008,  # TOKEN_QUERY
                ctypes.byref(token),
            ):
                return False, (
                    "OpenProcessToken failed with Windows error "
                    f"{ctypes.get_last_error()}"
                )
            token_size = wintypes.DWORD()
            get_token_information(
                token,
                1,  # TokenUser
                None,
                0,
                ctypes.byref(token_size),
            )
            if token_size.value == 0:
                return False, (
                    "GetTokenInformation sizing failed with Windows error "
                    f"{ctypes.get_last_error()}"
                )
            token_buffer = ctypes.create_string_buffer(token_size.value)
            if not get_token_information(
                token,
                1,
                token_buffer,
                token_size,
                ctypes.byref(token_size),
            ):
                return False, (
                    "GetTokenInformation failed with Windows error "
                    f"{ctypes.get_last_error()}"
                )
            token_user = ctypes.cast(
                token_buffer, ctypes.POINTER(_SidAndAttributes)
            ).contents
            if not token_user.Sid or not equal_sid(owner, token_user.Sid):
                return False, "object owner is not the current process user"

            for sid_text in ("S-1-5-18", "S-1-3-4"):  # SYSTEM, OWNER RIGHTS
                sid = wintypes.LPVOID()
                if not convert_sid(sid_text, ctypes.byref(sid)):
                    return False, (
                        "ConvertStringSidToSidW failed with Windows error "
                        f"{ctypes.get_last_error()}"
                    )
                expected_sids.append(sid)

            acl_info = _AclSizeInformation()
            if not get_acl_information(
                dacl,
                ctypes.byref(acl_info),
                ctypes.sizeof(acl_info),
                2,  # AclSizeInformation
            ):
                return False, (
                    "GetAclInformation failed with Windows error "
                    f"{ctypes.get_last_error()}"
                )
            if acl_info.AceCount != 2:
                return False, f"DACL contains {acl_info.AceCount} ACEs instead of 2"

            seen = [False, False]
            sid_offset = _AccessAllowedAce.SidStart.offset
            # A SID contains an 8-byte fixed header before any subauthorities.
            # Check the ACE boundary before asking Win32 to inspect the SID so
            # a malformed short ACE cannot make validation read into its
            # successor.
            minimum_ace_size = sid_offset + 8
            for index in range(acl_info.AceCount):
                ace_pointer = wintypes.LPVOID()
                if not get_ace(dacl, index, ctypes.byref(ace_pointer)):
                    return False, (
                        f"GetAce({index}) failed with Windows error "
                        f"{ctypes.get_last_error()}"
                    )
                ace = ctypes.cast(
                    ace_pointer, ctypes.POINTER(_AccessAllowedAce)
                ).contents
                if ace.Header.AceType != 0:  # ACCESS_ALLOWED_ACE_TYPE
                    return False, f"DACL ACE {index} is not a simple allow ACE"
                if ace.Header.AceFlags != 0:
                    return False, f"DACL ACE {index} has inheritance flags"
                if ace.Header.AceSize < minimum_ace_size:
                    return False, f"DACL ACE {index} is truncated"
                if ace.Mask != 0x001F01FF:  # FILE_ALL_ACCESS
                    return False, f"DACL ACE {index} does not grant exact full control"
                sid_pointer = wintypes.LPVOID(ace_pointer.value + sid_offset)
                if not is_valid_sid(sid_pointer):
                    return False, f"DACL ACE {index} contains an invalid SID"
                if get_length_sid(sid_pointer) != ace.Header.AceSize - sid_offset:
                    return False, f"DACL ACE {index} has inconsistent SID length"
                matches = [
                    bool(equal_sid(sid_pointer, expected))
                    for expected in expected_sids
                ]
                if matches.count(True) != 1:
                    return False, f"DACL ACE {index} grants an unexpected principal"
                matched_index = matches.index(True)
                if seen[matched_index]:
                    return False, f"DACL ACE {index} duplicates a principal"
                seen[matched_index] = True
            if not all(seen):
                return False, "DACL is missing SYSTEM or OWNER RIGHTS"
            return True, ""
        finally:
            for sid in expected_sids:
                if sid.value:
                    kernel32.LocalFree(sid)
            if token.value:
                kernel32.CloseHandle(token)
            if descriptor.value:
                kernel32.LocalFree(descriptor)
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        return False, f"unable to inspect Windows DACL: {exc}"


def _assert_windows_owner_only(path: Path, *, kind: str) -> None:
    valid, reason = _inspect_windows_owner_only(path)
    if not valid:
        raise SidecarPermissionError(
            f"{kind} does not have the required protected owner-only Windows DACL: "
            f"{path} ({reason})"
        )


def _harden_owner_only(
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
        if not _set_windows_owner_only(target) and strict:
            raise SidecarPermissionError(
                f"unable to apply an owner-only Windows DACL to {kind} {target}"
            )
        if strict:
            _assert_windows_owner_only(target, kind=kind)
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


def _harden_permissions(
    path: str | os.PathLike[str], *, strict: bool
) -> None:
    """Apply owner-only ``0600`` permissions to a file artifact."""

    _harden_owner_only(
        path,
        mode=0o600,
        strict=strict,
        kind="file",
    )


def _harden_directory_permissions(
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
    _harden_owner_only(
        target,
        mode=0o700,
        strict=strict,
        kind="directory",
    )


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _expect_keys(
    value: Any,
    *,
    name: str,
    required: set[str],
    optional: set[str] = frozenset(),
) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SidecarMalformedError(f"{name} must be an object")
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise SidecarMalformedError(f"{name} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise SidecarMalformedError(
            f"{name} contains unknown fields: {', '.join(sorted(unknown))}"
        )
    return value


def _expect_string(value: Any, name: str, *, max_length: int = 4096) -> str:
    if not isinstance(value, str) or len(value) > max_length:
        raise SidecarMalformedError(f"{name} must be a bounded string")
    return value


def _expect_int(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SidecarMalformedError(f"{name} must be an integer >= {minimum}")
    return value


def _expect_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise SidecarMalformedError(f"{name} must be a boolean")
    return value


def _expect_uuid(value: Any, name: str) -> str:
    text = _expect_string(value, name, max_length=64)
    try:
        UUID(text)
    except (ValueError, AttributeError) as exc:
        raise SidecarMalformedError(f"{name} must be a UUID") from exc
    return text


def _expect_timestamp(value: Any, name: str) -> str:
    text = _expect_string(value, name, max_length=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SidecarMalformedError(f"{name} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise SidecarMalformedError(f"{name} must include a timezone")
    return text


def _validate_file_identity(value: Any, name: str) -> None:
    if value is None:
        return
    data = _expect_keys(
        value,
        name=name,
        required={"platform"},
        optional={"device", "inode", "volume_serial", "file_index"},
    )
    platform = _expect_string(data["platform"], f"{name}.platform", max_length=16)
    expected = (
        {"volume_serial", "file_index"}
        if platform == "windows"
        else {"device", "inode"}
    )
    for key in expected:
        if key not in data or data[key] is None:
            raise SidecarMalformedError(f"{name}.{key} is required")
        _expect_int(data[key], f"{name}.{key}")


def validate_sidecar_payload(value: Any) -> Mapping[str, Any]:
    """Validate every schema-v2 field before model construction."""

    data = _expect_keys(
        value,
        name="sidecar",
        required={
            "schema_version",
            "record_kind",
            "record_revision",
            "lease_id",
            "generation",
            "token_fingerprint",
            "document",
            "owner",
            "lease",
            "document_state",
        },
        optional={"migration"},
    )
    if data["schema_version"] != SCHEMA_VERSION:
        raise SidecarMalformedError(
            f"unsupported sidecar schema version: {data['schema_version']!r}"
        )
    if data["record_kind"] != RECORD_KIND:
        raise SidecarMalformedError("unrecognized sidecar record_kind")
    _expect_int(data["record_revision"], "record_revision", minimum=1)
    _expect_uuid(data["lease_id"], "lease_id")
    _expect_int(data["generation"], "generation", minimum=1)
    fingerprint = _expect_string(
        data["token_fingerprint"], "token_fingerprint", max_length=80
    )
    if not TOKEN_FINGERPRINT_RE.fullmatch(fingerprint):
        raise SidecarMalformedError("token_fingerprint must contain a SHA-256 digest")

    document = _expect_keys(
        data["document"],
        name="document",
        required={
            "session_uuid",
            "name",
            "canonical_path",
            "comparison_key",
            "file_identity",
        },
    )
    _expect_uuid(document["session_uuid"], "document.session_uuid")
    _expect_string(document["name"], "document.name", max_length=512)
    for field in ("canonical_path", "comparison_key"):
        if document[field] is not None:
            _expect_string(document[field], f"document.{field}")
    if bool(document["canonical_path"]) != bool(document["comparison_key"]):
        raise SidecarMalformedError(
            "canonical_path and comparison_key must both be set or both be null"
        )
    _validate_file_identity(document["file_identity"], "document.file_identity")

    migration = data.get("migration")
    if migration is not None:
        migration = _expect_keys(
            migration,
            name="migration",
            required={"migration_id", "source", "destination", "role"},
        )
        _expect_uuid(migration["migration_id"], "migration.migration_id")
        source = _expect_keys(
            migration["source"],
            name="migration.source",
            required={"canonical_path", "comparison_key"},
        )
        destination = _expect_keys(
            migration["destination"],
            name="migration.destination",
            required={"canonical_path", "comparison_key"},
        )
        for field in ("canonical_path", "comparison_key"):
            if source[field] is not None:
                _expect_string(source[field], f"migration.source.{field}")
            _expect_string(
                destination[field], f"migration.destination.{field}"
            )
        if bool(source["canonical_path"]) != bool(source["comparison_key"]):
            raise SidecarMalformedError(
                "migration source canonical_path and comparison_key must both be set or both be null"
            )
        if not destination["canonical_path"] or not destination["comparison_key"]:
            raise SidecarMalformedError(
                "migration destination path identity must not be empty"
            )
        if (
            source["comparison_key"] is not None
            and source["comparison_key"] == destination["comparison_key"]
        ):
            raise SidecarMalformedError(
                "migration source and destination must identify different paths"
            )
        role = _expect_string(migration["role"], "migration.role", max_length=16)
        if role not in {"source", "destination"}:
            raise SidecarMalformedError("migration.role is invalid")
        endpoint = source if role == "source" else destination
        if role == "source" and endpoint["canonical_path"] is None:
            raise SidecarMalformedError(
                "a source migration record requires a saved source path"
            )
        if (
            document["canonical_path"] != endpoint["canonical_path"]
            or document["comparison_key"] != endpoint["comparison_key"]
        ):
            raise SidecarMalformedError(
                "migration role identity does not match the sidecar document"
            )

    owner_fields = {
        "addon_profile_id",
        "addon_runtime_id",
        "freecad_pid",
        "freecad_process_started_at",
        "boot_id",
        "mcp_instance_id",
        "mcp_pid",
        "mcp_process_started_at",
        "hostname",
        "client",
        "agent_id",
    }
    owner = _expect_keys(data["owner"], name="owner", required=owner_fields)
    _expect_uuid(owner["addon_profile_id"], "owner.addon_profile_id")
    _expect_uuid(owner["addon_runtime_id"], "owner.addon_runtime_id")
    _expect_uuid(owner["mcp_instance_id"], "owner.mcp_instance_id")
    _expect_int(owner["freecad_pid"], "owner.freecad_pid", minimum=1)
    _expect_int(owner["mcp_pid"], "owner.mcp_pid", minimum=1)
    for field in owner_fields - {"freecad_pid", "mcp_pid"}:
        if field not in {"addon_profile_id", "addon_runtime_id", "mcp_instance_id"}:
            _expect_string(owner[field], f"owner.{field}", max_length=512)
    _expect_timestamp(
        owner["freecad_process_started_at"], "owner.freecad_process_started_at"
    )
    _expect_timestamp(
        owner["mcp_process_started_at"], "owner.mcp_process_started_at"
    )

    lease = _expect_keys(
        data["lease"],
        name="lease",
        required={
            "state",
            "state_revision",
            "acquired_at",
            "last_heartbeat_at",
            "heartbeat_sequence",
            "current_operation",
            "task_summary",
        },
    )
    try:
        LeaseState(lease["state"])
    except (ValueError, TypeError) as exc:
        raise SidecarMalformedError("lease.state is invalid") from exc
    _expect_int(lease["state_revision"], "lease.state_revision", minimum=1)
    _expect_int(lease["heartbeat_sequence"], "lease.heartbeat_sequence")
    _expect_timestamp(lease["acquired_at"], "lease.acquired_at")
    _expect_timestamp(lease["last_heartbeat_at"], "lease.last_heartbeat_at")
    _expect_string(lease["current_operation"], "lease.current_operation", max_length=512)
    _expect_string(lease["task_summary"], "lease.task_summary", max_length=1024)

    state = _expect_keys(
        data["document_state"],
        name="document_state",
        required={
            "dirty",
            "user_intervened",
            "last_mutation_revision",
            "last_successful_save_at",
            "last_verified_save_revision",
            "baseline",
            "error",
            "validation_complete",
            "snapshot_id",
        },
    )
    _expect_bool(state["dirty"], "document_state.dirty")
    _expect_bool(state["user_intervened"], "document_state.user_intervened")
    _expect_bool(state["validation_complete"], "document_state.validation_complete")
    _expect_int(
        state["last_mutation_revision"], "document_state.last_mutation_revision"
    )
    _expect_int(
        state["last_verified_save_revision"],
        "document_state.last_verified_save_revision",
    )
    for field in ("last_successful_save_at", "snapshot_id"):
        if state[field] is not None:
            _expect_string(state[field], f"document_state.{field}", max_length=512)
    if state["last_successful_save_at"] is not None:
        _expect_timestamp(
            state["last_successful_save_at"],
            "document_state.last_successful_save_at",
        )

    if state["baseline"] is not None:
        baseline = _expect_keys(
            state["baseline"],
            name="document_state.baseline",
            required={"mtime_ns", "size", "sha256", "file_identity"},
        )
        _expect_int(baseline["mtime_ns"], "baseline.mtime_ns")
        _expect_int(baseline["size"], "baseline.size")
        sha = _expect_string(baseline["sha256"], "baseline.sha256", max_length=64)
        if len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha):
            raise SidecarMalformedError("baseline.sha256 must be lowercase SHA-256")
        _validate_file_identity(baseline["file_identity"], "baseline.file_identity")

    if state["error"] is not None:
        error_data = _expect_keys(
            state["error"],
            name="document_state.error",
            required={"code", "message", "at", "request_id"},
        )
        for field, maximum in (("code", 128), ("message", 2048), ("at", 64)):
            _expect_string(error_data[field], f"error.{field}", max_length=maximum)
        _expect_timestamp(error_data["at"], "error.at")
        if error_data["request_id"] is not None:
            _expect_string(error_data["request_id"], "error.request_id", max_length=64)
    if data["record_revision"] < lease["state_revision"]:
        raise SidecarMalformedError("record_revision cannot predate state_revision")
    if state["last_verified_save_revision"] > state["last_mutation_revision"]:
        raise SidecarMalformedError(
            "last_verified_save_revision cannot exceed last_mutation_revision"
        )
    if lease["state"] == LeaseState.USER_INTERVENED.value and not state[
        "user_intervened"
    ]:
        raise SidecarMalformedError(
            "USER_INTERVENED state requires user_intervened=true"
        )
    if lease["state"] == LeaseState.LOCKED_ERROR.value and state["error"] is None:
        raise SidecarMalformedError("LOCKED_ERROR state requires structured error metadata")
    return data


def parse_sidecar_bytes(data: bytes, *, max_bytes: int = MAX_SIDECAR_BYTES) -> LeaseRecord:
    if len(data) > max_bytes:
        raise SidecarTooLargeError(
            f"sidecar exceeds the {max_bytes}-byte safety limit"
        )
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SidecarMalformedError(f"sidecar is not valid UTF-8 JSON: {exc}") from exc
    validated = validate_sidecar_payload(value)
    try:
        return LeaseRecord.from_sidecar_dict(validated)
    except (KeyError, TypeError, ValueError) as exc:
        raise SidecarMalformedError(f"sidecar record is invalid: {exc}") from exc


def _serialize_record(
    record: LeaseRecord,
    *,
    max_bytes: int,
    persist_task_summary: bool = False,
) -> bytes:
    encoded = json.dumps(
        record.to_sidecar_dict(include_task_summary=persist_task_summary),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > max_bytes:
        raise SidecarTooLargeError(
            f"serialized sidecar exceeds the {max_bytes}-byte safety limit"
        )
    # Validate our own output so invalid in-memory records cannot reach disk.
    parse_sidecar_bytes(encoded, max_bytes=max_bytes)
    return encoded


def _assert_regular_not_symlink(
    path: Path, *, strict_permissions: bool
) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise SidecarNotFoundError(str(path)) from None
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    if stat.S_ISLNK(info.st_mode) or file_attributes & reparse_flag:
        raise SidecarMalformedError(
            f"sidecar must not be a symlink or reparse point: {path}"
        )
    if not stat.S_ISREG(info.st_mode):
        raise SidecarMalformedError(f"sidecar must be a regular file: {path}")
    if strict_permissions and os.name != "nt":
        mode = stat.S_IMODE(info.st_mode)
        if mode != 0o600:
            raise SidecarPermissionError(
                f"sidecar permissions must be exactly owner-only 0600: {path}"
            )
    elif strict_permissions:
        _assert_windows_owner_only(path, kind="sidecar file")


def _read_record(
    path: Path, *, max_bytes: int, strict_permissions: bool
) -> LeaseRecord:
    _assert_regular_not_symlink(
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


def _write_temp(
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
        _harden_permissions(temp_path, strict=strict_permissions)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return temp_path
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def _matches_cas(current: LeaseRecord, expected: LeaseRecord) -> bool:
    return (
        current.lease_id == expected.lease_id
        and current.generation == expected.generation
        and current.token_fingerprint == expected.token_fingerprint
        and current.record_revision == expected.record_revision
        and current.document.session_uuid == expected.document.session_uuid
        and current.migration == expected.migration
    )


class SidecarStore:
    """Atomic guarded create/replace/delete with strict compare-and-swap."""

    def __init__(
        self,
        *,
        max_bytes: int = MAX_SIDECAR_BYTES,
        strict_permissions: bool = True,
        allow_network: bool = False,
        persist_task_summary: bool = False,
        network_detector: Callable[[Path], bool] = _is_network_path,
    ) -> None:
        if not isinstance(persist_task_summary, bool):
            raise TypeError("persist_task_summary must be true or false")
        self.max_bytes = max_bytes
        self.strict_permissions = strict_permissions
        self.allow_network = allow_network
        self.persist_task_summary = persist_task_summary
        self.network_detector = network_detector

    def _check_target(self, path: Path) -> None:
        if self.network_detector(path) and not self.allow_network:
            raise SidecarNetworkPathError(
                f"network sidecars require an explicit lower-assurance override: {path}"
            )
        if not path.parent.is_dir():
            raise SidecarError(f"sidecar parent directory does not exist: {path.parent}")

    def guard(self, path: str | os.PathLike[str]) -> contextlib.AbstractContextManager[None]:
        sidecar = Path(path)
        self._check_target(sidecar)
        return _native_guard(
            guard_path_for(sidecar), strict_permissions=self.strict_permissions
        )

    def read(self, path: str | os.PathLike[str]) -> LeaseRecord:
        sidecar = Path(path)
        self._check_target(sidecar)
        return _read_record(
            sidecar,
            max_bytes=self.max_bytes,
            strict_permissions=self.strict_permissions,
        )

    def create(self, path: str | os.PathLike[str], record: LeaseRecord) -> None:
        sidecar = Path(path)
        self._check_target(sidecar)
        payload = _serialize_record(
            record,
            max_bytes=self.max_bytes,
            persist_task_summary=self.persist_task_summary,
        )
        with _native_guard(
            guard_path_for(sidecar), strict_permissions=self.strict_permissions
        ):
            if os.path.lexists(sidecar):
                # Do not parse/delete here: malformed and stale records are still
                # conflicts that need an explicit recovery workflow.
                raise SidecarExistsError(str(sidecar))
            temporary = _write_temp(
                sidecar, payload, strict_permissions=self.strict_permissions
            )
            try:
                try:
                    os.link(temporary, sidecar)
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
                _harden_permissions(sidecar, strict=self.strict_permissions)
                _fsync_directory(sidecar.parent)
            finally:
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def replace(
        self,
        path: str | os.PathLike[str],
        record: LeaseRecord,
        *,
        expected: LeaseRecord,
    ) -> None:
        sidecar = Path(path)
        self._check_target(sidecar)
        if record.record_revision != expected.record_revision + 1:
            raise SidecarConflictError(
                "replacement record_revision must be exactly one greater than expected"
            )
        payload = _serialize_record(
            record,
            max_bytes=self.max_bytes,
            persist_task_summary=self.persist_task_summary,
        )
        with _native_guard(
            guard_path_for(sidecar), strict_permissions=self.strict_permissions
        ):
            current = _read_record(
                sidecar,
                max_bytes=self.max_bytes,
                strict_permissions=self.strict_permissions,
            )
            if not _matches_cas(current, expected):
                raise SidecarConflictError("sidecar changed before replacement")
            temporary = _write_temp(
                sidecar, payload, strict_permissions=self.strict_permissions
            )
            try:
                os.replace(temporary, sidecar)
                _harden_permissions(sidecar, strict=self.strict_permissions)
                _fsync_directory(sidecar.parent)
            except Exception:
                try:
                    temporary.unlink()
                except OSError:
                    pass
                raise

    def delete(
        self, path: str | os.PathLike[str], *, expected: LeaseRecord
    ) -> None:
        sidecar = Path(path)
        self._check_target(sidecar)
        with _native_guard(
            guard_path_for(sidecar), strict_permissions=self.strict_permissions
        ):
            current = _read_record(
                sidecar,
                max_bytes=self.max_bytes,
                strict_permissions=self.strict_permissions,
            )
            if not _matches_cas(current, expected):
                raise SidecarConflictError("sidecar changed before deletion")
            try:
                sidecar.unlink()
            except FileNotFoundError:
                raise SidecarConflictError("sidecar disappeared before deletion") from None
            except OSError as exc:
                raise SidecarError(f"unable to delete sidecar {sidecar}: {exc}") from exc
            _fsync_directory(sidecar.parent)
