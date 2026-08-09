"""ctypes layout for a Win32 SID_AND_ATTRIBUTES entry."""

from __future__ import annotations

import ctypes
from ctypes import wintypes


class SidAndAttributes(ctypes.Structure):
    _fields_ = [
        ("Sid", wintypes.LPVOID),
        ("Attributes", wintypes.DWORD),
    ]
