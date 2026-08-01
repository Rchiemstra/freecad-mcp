"""ctypes layout for Win32 ACL_SIZE_INFORMATION."""

from __future__ import annotations

import ctypes
from ctypes import wintypes


class AclSizeInformation(ctypes.Structure):
    _fields_ = [
        ("AceCount", wintypes.DWORD),
        ("AclBytesInUse", wintypes.DWORD),
        ("AclBytesFree", wintypes.DWORD),
    ]
