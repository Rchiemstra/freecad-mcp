"""Best-effort kill-on-close Job Object without a pywin32 dependency."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from .extended_limit import EXTENDED_LIMIT


class WindowsJobObject:
    """Best-effort kill-on-close Job Object without a pywin32 dependency."""

    def __init__(self) -> None:
        self.handle = None

    def assign(self, process_handle: int) -> None:
        if sys.platform != "win32":
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        info = EXTENDED_LIMIT()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        ):
            kernel32.CloseHandle(handle)
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
        if not kernel32.AssignProcessToJobObject(handle, wintypes.HANDLE(process_handle)):
            kernel32.CloseHandle(handle)
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        self.handle = handle

    def terminate(self, exit_code: int = 1) -> None:
        if self.handle is not None and sys.platform == "win32":
            ctypes.WinDLL("kernel32", use_last_error=True).TerminateJobObject(
                self.handle, exit_code
            )

    def close(self) -> None:
        if self.handle is not None and sys.platform == "win32":
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self.handle)
            self.handle = None
