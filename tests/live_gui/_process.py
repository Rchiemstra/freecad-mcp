"""Small process and diagnostic helpers; no FreeCAD or MCP imports."""

from __future__ import annotations

import json
import os
import select
import signal
import sys
from pathlib import Path

LOG_TAIL_BYTES = 64 * 1024


def tail(path: Path, lines: int) -> str:
    """Read at most 64 KiB, including when a native log has no newlines."""
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - LOG_TAIL_BYTES))
            data = stream.read(LOG_TAIL_BYTES)
    except OSError as exc:
        return f"[unavailable: {exc}]\n"
    text = b"".join(data.splitlines(keepends=True)[-lines:]).decode("utf-8", errors="replace")
    # Invalid native output can expand to three UTF-8 bytes per replacement.
    return text.encode("utf-8")[-LOG_TAIL_BYTES:].decode("utf-8", errors="ignore")


class ProcessMonitor:
    """Read the raw child status retained by the isolated launcher."""

    def __init__(self, launcher, status_file: Path, pid: int | None = None):
        self.launcher = launcher
        self.status_file = status_file
        self._pidfd = None
        self._exited = False
        if pid is not None and hasattr(os, "pidfd_open"):
            try:
                self._pidfd = os.pidfd_open(pid)
            except ProcessLookupError:
                self._exited = True
            except OSError:
                # Older kernels and restricted runners may lack pidfd support.
                pass

    def close(self) -> None:
        if self._pidfd is not None:
            os.close(self._pidfd)
            self._pidfd = None

    def poll(self) -> int | None:
        # Poll first: an exited launcher must have finished publishing status.
        launcher_code = self.launcher.poll()
        try:
            code = json.loads(self.status_file.read_text())["returncode"]
        except FileNotFoundError:
            code = None
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Invalid FreeCAD exit status: {exc}") from exc
        if code is not None:
            if type(code) is not int:
                raise RuntimeError(f"Invalid FreeCAD exit status: {code!r}")
            return code
        # On Linux observe death directly, then let the owning launcher
        # publish status. This closes the death-to-status-file race.
        if self._pidfd is not None and select.select([self._pidfd], [], [], 0)[0]:
            self._exited = True
            self.close()
        if launcher_code is None and self._exited:
            self.launcher.wait(timeout=5)
            return self.poll()
        if launcher_code is not None:
            raise RuntimeError(
                f"FreeCAD launcher exited ({launcher_code}) without child exit status"
            )
        return None


def recover_if_dead(process, workdir: Path, nodeid: str, restart) -> bool:
    """Print crash evidence before retiring logs/client and starting afresh."""
    code = process.poll()
    if code is None:
        return False
    name = "none"
    if code < 0:
        try:
            name = signal.Signals(-code).name
        except ValueError:
            name = f"UNKNOWN({-code})"
    stream = sys.__stderr__
    stream.write(f"FREECAD DIED during {nodeid}: exit={code} signal={name}\n")
    for filename, lines in (("freecad_output.log", 200), ("freecad.log", 100)):
        stream.write(f"--- {filename} (last {lines} lines, max {LOG_TAIL_BYTES} bytes) ---\n")
        stream.write(tail(workdir / filename, lines))
        stream.write("\n")
    stream.flush()
    restart()
    return True
