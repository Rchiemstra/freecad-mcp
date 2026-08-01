"""One-class Windows job-object ctypes structures."""

from .basic_limit import BASIC_LIMIT
from .extended_limit import EXTENDED_LIMIT
from .io_counters import IO_COUNTERS

__all__ = [
    "BASIC_LIMIT",
    "EXTENDED_LIMIT",
    "IO_COUNTERS",
]
