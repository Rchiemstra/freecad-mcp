"""Child-process tree management for the instrumented MCP launcher (R2)."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import Iterable


def _iter_descendant_pids(root_pid: int) -> list[int]:
    """Return all descendant PIDs of *root_pid* (best effort, cross-platform)."""
    if sys.platform == "win32":
        return _win_descendants(root_pid)
    return _posix_descendants(root_pid)


def _posix_descendants(root_pid: int) -> list[int]:
    try:
        out = subprocess.check_output(
            ["ps", "-o", "pid=", "--ppid", str(root_pid)],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    children = [int(line.strip()) for line in out.splitlines() if line.strip().isdigit()]
    result: list[int] = []
    for pid in children:
        result.append(pid)
        result.extend(_posix_descendants(pid))
    return result


def _win_descendants(root_pid: int) -> list[int]:
    try:
        out = subprocess.check_output(
            [
                "wmic",
                "process",
                "where",
                f"ParentProcessId={root_pid}",
                "get",
                "ProcessId",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pid = int(line)
            pids.append(pid)
            pids.extend(_win_descendants(pid))
    return pids


def kill_process_tree(root_pid: int, *, grace_seconds: float = 2.0) -> None:
    """Terminate *root_pid* and all descendants."""
    pids = [root_pid, *_iter_descendant_pids(root_pid)]
    for pid in pids:
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    if sys.platform != "win32":
        deadline = time.time() + grace_seconds
        while time.time() < deadline:
            alive = [pid for pid in pids if _pid_alive(pid)]
            if not alive:
                return
            time.sleep(0.1)
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def count_matching_processes(name_substrings: Iterable[str]) -> int:
    """Count live processes whose command line contains all substrings."""
    needles = tuple(name_substrings)
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["wmic", "process", "get", "ProcessId,CommandLine"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return 0
        count = 0
        for line in out.splitlines():
            if all(n.lower() in line.lower() for n in needles):
                count += 1
        return count
    try:
        out = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
    except Exception:
        return 0
    count = 0
    for line in out.splitlines()[1:]:
        if all(n in line for n in needles):
            count += 1
    return count


class WindowsJobObject:
    """Assign a child process tree to a Windows Job Object with kill-on-close."""

    def __init__(self) -> None:
        self._handle = None

    def assign(self, pid: int) -> None:
        if sys.platform != "win32":
            return
        try:
            import win32api  # type: ignore[import-untyped]
            import win32con  # type: ignore[import-untyped]
            import win32job  # type: ignore[import-untyped]
        except ImportError:
            return
        self._handle = win32job.CreateJobObject(None, "")
        info = win32job.QueryInformationJobObject(
            self._handle, win32job.JobObjectExtendedLimitInformation
        )
        info["BasicLimitInformation"]["LimitFlags"] = (
            win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        win32job.SetInformationJobObject(
            self._handle,
            win32job.JobObjectExtendedLimitInformation,
            info,
        )
        proc = win32api.OpenProcess(win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, pid)
        win32job.AssignProcessToJobObject(self._handle, proc)
        win32api.CloseHandle(proc)

    def close(self) -> None:
        if self._handle is not None:
            try:
                import win32api  # type: ignore[import-untyped]

                win32api.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None

    def __enter__(self) -> WindowsJobObject:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
