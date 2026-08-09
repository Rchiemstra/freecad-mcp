"""ctypes layout for the Win32 OVERLAPPED structure."""

from __future__ import annotations

import ctypes
from ctypes import wintypes


class OverlappedStruct(ctypes.Structure):
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
