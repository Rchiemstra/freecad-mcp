"""Discover and probe matching FreeCADCmd executables."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ..process_control_ops.terminate import popen_platform_options
from .build_identity import require_compatible_builds
from .worker_version_mismatch import WorkerVersionMismatch

if TYPE_CHECKING:
    from .worker_runtime import WorkerRuntime

_VERSION_RE = re.compile(
    r"FreeCAD\s+(\d+)\.(\d+)\.(\d+)(?:[^\r\n]*?Revision:\s*([^\r\n]+))?"
)
VERSION_PROBE_TIMEOUT_SECONDS = 15


def candidate_paths(runtime: WorkerRuntime) -> list[Path]:
    names = (
        ("FreeCADCmd.exe", "freecadcmd.exe")
        if sys.platform == "win32"
        else ("FreeCADCmd", "freecadcmd")
    )
    candidates: list[Path] = []
    gui = Path(runtime.gui_executable)
    candidates.extend(gui.with_name(name) for name in names)
    home_bin = Path(runtime.freecad_home) / "bin"
    candidates.extend(home_bin / name for name in names)
    if runtime.configured_path:
        candidates.append(Path(runtime.configured_path))
    env_path = os.environ.get("FREECAD_MCP_FREECADCMD")
    if env_path:
        candidates.append(Path(env_path))
    for name in names:
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    unique = []
    seen = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(str(candidate)))
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def probe_version(candidate: Path) -> tuple[str, str, str, str]:
    completed = subprocess.run(
        [str(candidate), "--version"],
        capture_output=True,
        text=True,
        timeout=VERSION_PROBE_TIMEOUT_SECONDS,
        check=False,
        **popen_platform_options(),
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise RuntimeError(f"--version exited {completed.returncode}: {output.strip()}")
    match = _VERSION_RE.search(output)
    if not match:
        raise RuntimeError(f"could not parse FreeCAD version: {output.strip()}")
    groups = match.groups()
    return (
        groups[0].strip(),
        groups[1].strip(),
        groups[2].strip(),
        (groups[3] or "").strip(),
    )


def discover_executable(manager) -> Path:
    if manager._executable is not None:
        return manager._executable
    expected = manager.runtime.gui_version
    failures = []
    mismatches = []
    for candidate in manager._candidate_paths():
        if not candidate.is_file():
            continue
        try:
            actual = manager._probe_version(candidate)
            require_compatible_builds(expected, actual)
            manager._executable = candidate.resolve()
            manager._executable_version = actual
            manager._last_error = None
            return manager._executable
        except WorkerVersionMismatch as exc:
            message = f"{candidate}: {exc}"
            failures.append(message)
            mismatches.append(message)
        except Exception as exc:
            failures.append(f"{candidate}: {exc}")
    manager._last_error = "; ".join(failures) or "No FreeCADCmd executable found"
    if mismatches:
        raise WorkerVersionMismatch(manager._last_error)
    raise RuntimeError(manager._last_error)
