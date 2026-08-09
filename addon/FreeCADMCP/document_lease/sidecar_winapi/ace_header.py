"""ctypes layout for a Win32 ACE header."""

from __future__ import annotations

import ctypes
from ctypes import wintypes


class AceHeader(ctypes.Structure):
    _fields_ = [
        ("AceType", wintypes.BYTE),
        ("AceFlags", wintypes.BYTE),
        ("AceSize", wintypes.WORD),
    ]
