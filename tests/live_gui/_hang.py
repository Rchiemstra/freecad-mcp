"""Detect a live FreeCAD that has stopped answering, and dump its stacks.

A single slow RPC is not a hang: the call must miss its deadline and a short
follow-up probe must also get no answer while the process is still alive.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Short enough that a stuck GUI cannot cost another full RPC deadline, long
# enough that an idle FreeCAD answers list_documents.
PROBE_TIMEOUT_SECONDS = 5.0
# Symbol load on a RelWithDebInfo FreeCAD is the slow part. Bound it.
GDB_TIMEOUT_SECONDS = 60.0
# One restart, then stop. Two deadlines plus two dumps stay within a few minutes.
MAX_HANGS = 2
REPORT_NAME = "freecad-hang.txt"
_FRAME = re.compile(r"^#0\s", re.MULTILINE)

# PR_SET_PTRACER survives exec and does not survive fork (Yama ptrace_scope=1).
# start_freecad_isolated._command_with_ptrace_permit therefore execs FreeCAD
# from a helper that has already called prctl, keeping Popen.pid. Same prctl
# value as .github/scripts/run_gui_tests.py.

_DEADLINE_MARKERS = (
    "FreeCAD JSON-RPC response deadline exceeded",
    "failed (TimeoutError)",
    "waiting for FreeCAD GUI response",
    "still executing a request that timed out",
    "GUI dispatch timed out",
)


class FreeCadHung(RuntimeError):
    """The FreeCAD process is alive and stopped answering RPC."""


def is_rpc_deadline(exc: BaseException | None, text: str | None) -> bool:
    """True when this call hit a transport or GUI-dispatch deadline."""
    if isinstance(exc, TimeoutError):
        return True
    blob = text or ""
    return any(marker in blob for marker in _DEADLINE_MARKERS)


def ptrace_scope() -> str:
    path = Path("/proc/sys/kernel/yama/ptrace_scope")
    try:
        return path.read_text(encoding="utf-8").strip() or "empty"
    except OSError as exc:
        return f"unreadable ({exc})"


def _kill_process_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def collect_native_backtraces(pid: int, *, timeout: float = GDB_TIMEOUT_SECONDS) -> str:
    """All-thread native backtraces, plus Python stacks when gdb can print them."""
    gdb = shutil.which("gdb")
    scope = ptrace_scope()
    if not gdb:
        return (
            "Cannot collect native backtraces: gdb is not installed.\n"
            f"yama ptrace_scope={scope}\n"
        )
    args = [
        gdb,
        "-batch",
        "-ex",
        "set pagination off",
        "-ex",
        "set confirm off",
        "-p",
        str(pid),
        "-ex",
        "thread apply all bt 30",
        "-ex",
        "info threads",
        "-ex",
        (
            "python exec("
            "\"import gdb\\n"
            "try:\\n"
            "    gdb.execute('thread apply all py-bt')\\n"
            "except Exception as exc:\\n"
            "    gdb.write('Python stacks unavailable: %s\\\\n' % exc)\\n"
            "\""
            ")"
        ),
        "-ex",
        "detach",
    ]
    output = _run_gdb(args, timeout)
    if _FRAME.search(output):
        return output
    return (
        f"gdb could not attach to FreeCAD pid {pid} "
        f"(yama ptrace_scope={scope}).\n{output}"
    )


def _run_gdb(args: list[str], timeout: float) -> str:
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            start_new_session=True,
            env={**os.environ, "DEBUGINFOD_URLS": ""},
        )
    except OSError as exc:
        return f"gdb failed to start: {exc}\n"
    try:
        output, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        _kill_process_group(proc)
        try:
            rest, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            rest = ""
        text = f"{partial or ''}{rest or ''}"
        return text + "\ngdb diagnostic timed out.\n"
    text = output or ""
    if proc.returncode not in (0, None) and not text:
        text = f"gdb exited {proc.returncode} with no output.\n"
    return text


@dataclass(frozen=True)
class HangVerdict:
    hung: bool
    action: str
    message: str


class HangMonitor:
    """Count hangs and write one stack dump per stuck process."""

    def __init__(self, *, max_hangs: int = MAX_HANGS) -> None:
        self.max_hangs = max_hangs
        self.hang_count = 0

    def assess(
        self,
        *,
        poll,
        probe,
        pid: int,
        workdir: Path,
        nodeid: str,
        last_passed: str | None,
        collect,
        stop,
        trigger: str = "",
    ) -> HangVerdict:
        if poll() is not None:
            return HangVerdict(False, "none", "")
        try:
            answered = bool(probe())
        except Exception:
            answered = False
        # Died while the probe was in flight: the crash path owns that.
        if poll() is not None:
            return HangVerdict(False, "none", "")
        if answered:
            return HangVerdict(False, "none", "")
        report = collect(pid)
        message = _hang_message(self.hang_count + 1, nodeid, last_passed, self.max_hangs)
        _write_report(
            workdir,
            nodeid=nodeid,
            last_passed=last_passed,
            pid=pid,
            message=message,
            stacks=report,
            trigger=trigger,
        )
        stop()
        self.hang_count += 1
        action = "exit" if self.hang_count >= self.max_hangs else "restart"
        return HangVerdict(True, action, message)


def _hang_message(count: int, nodeid: str, last_passed: str | None, max_hangs: int) -> str:
    passed = last_passed or "none"
    if count >= max_hangs:
        return (
            f"FreeCAD stopped answering again during {nodeid} "
            f"(last passed: {passed}); ending the live GUI session"
        )
    return f"FreeCAD stopped answering during {nodeid} (last passed: {passed})"


def _write_report(
    workdir: Path,
    *,
    nodeid: str,
    last_passed: str | None,
    pid: int,
    message: str,
    stacks: str,
    trigger: str = "",
) -> None:
    flat = " ".join((trigger or "").split())
    if len(flat) > 400:
        flat = flat[:400] + "..."
    trigger_line = f"trigger: {flat}\n" if flat else ""
    body = (
        "FREECAD HUNG\n"
        f"test: {nodeid}\n"
        f"last passed: {last_passed or 'none'}\n"
        f"pid: {pid}\n"
        f"yama ptrace_scope: {ptrace_scope()}\n"
        f"{trigger_line}"
        f"{message}\n"
        "--- gdb ---\n"
        f"{stacks}"
    )
    if not body.endswith("\n"):
        body += "\n"
    # Keep the step log bounded if gdb prints every shared library.
    encoded = body.encode("utf-8", errors="replace")
    if len(encoded) > 200_000:
        body = encoded[:200_000].decode("utf-8", errors="ignore") + "\n[truncated]\n"
    path = workdir / REPORT_NAME
    with path.open("a", encoding="utf-8") as handle:
        handle.write(body)
    stream = sys.__stderr__
    stream.write(body)
    stream.flush()
