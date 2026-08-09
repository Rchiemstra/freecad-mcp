"""ctypes layout for a Win32 ACCESS_ALLOWED_ACE."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from .ace_header import AceHeader


class AccessAllowedAce(ctypes.Structure):
    _fields_ = [
        ("Header", AceHeader),
        ("Mask", wintypes.DWORD),
        ("SidStart", wintypes.DWORD),
    ]
