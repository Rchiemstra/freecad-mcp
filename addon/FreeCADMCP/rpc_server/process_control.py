"""Bounded process-tree termination for isolated FreeCADCmd workers."""

from __future__ import annotations

import contextlib
import ctypes
import os
import signal
import subprocess
import sys
from ctypes import wintypes

from .process_control_types.extended_limit import EXTENDED_LIMIT

CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


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


def popen_platform_options() -> dict:
    if sys.platform == "win32":
        return {"creationflags": CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW}
    return {"start_new_session": True}


def terminate_process_tree(
    process: subprocess.Popen, job_object: WindowsJobObject | None = None, grace: float = 2.0
) -> bool:
    if process.poll() is not None:
        return True
    if sys.platform == "win32":
        if job_object is not None:
            with contextlib.suppress(Exception):
                job_object.terminate(1)
        try:
            process.wait(timeout=grace)
            return True
        except subprocess.TimeoutExpired:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=max(grace, 1.0),
                check=False,
            )
    else:
        with contextlib.suppress(OSError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=grace)
            return True
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                os.killpg(process.pid, signal.SIGKILL)
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            process.kill()
    return process.poll() is not None
