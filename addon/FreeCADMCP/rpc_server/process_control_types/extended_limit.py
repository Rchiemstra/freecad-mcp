"""ctypes JOBOBJECT_EXTENDED_LIMIT_INFORMATION structure."""

from __future__ import annotations

import ctypes

from .basic_limit import BASIC_LIMIT
from .io_counters import IO_COUNTERS


class EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", BASIC_LIMIT),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]
