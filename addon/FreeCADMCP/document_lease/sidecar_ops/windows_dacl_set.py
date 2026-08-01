"""Apply a protected owner/system-only DACL on Windows."""

from __future__ import annotations

import os
from pathlib import Path


def set_windows_owner_only(path: Path) -> bool:
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
