"""Cross-platform subprocess spawn and termination helpers."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys

from ..process_control_types.windows_job_object import WindowsJobObject

CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


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
