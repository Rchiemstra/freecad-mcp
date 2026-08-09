"""Lazy ctypes OVERLAPPED holder kept alive for LockFileEx."""

from __future__ import annotations

from .overlapped_struct import OverlappedStruct


class _WindowsOverlapped:
    """Lazy ctypes OVERLAPPED holder, kept alive for LockFileEx."""

    def __init__(self) -> None:
        self.value = OverlappedStruct()
