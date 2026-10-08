"""Launch a real FreeCAD GUI with the MCP addon and drive it through the MCP server.

Requirements (the tests skip without them):

* ``FREECAD_MCP_ISOLATED_FREECAD``: absolute path of a FreeCAD GUI executable.
* ``DISPLAY``: an X server, e.g. ``xvfb-run -a`` or ``Xvfb :99``.

Everything FreeCAD prints (Report view errors, Coin and Qt warnings) is captured
and every test fails on new warning or error lines unless it allows them.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.live_gui._support import MCP_ROOT, GuiLog, McpClient


@dataclass
class LiveGui:
    pid: int
    manifest: Path
    workdir: Path
    logs: list[Path]


def _require_environment() -> Path:
    executable = os.environ.get("FREECAD_MCP_ISOLATED_FREECAD", "").strip()
    if not executable or not Path(executable).is_file():
        pytest.skip("FREECAD_MCP_ISOLATED_FREECAD does not name a FreeCAD GUI executable")
    if not os.environ.get("DISPLAY"):
        pytest.skip("live GUI tests need an X display (xvfb-run -a)")
    return Path(executable)


def _stop(pid: int) -> None:
    for sig, wait in ((signal.SIGTERM, 15.0), (signal.SIGKILL, 5.0)):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.2)


@pytest.fixture(scope="session")
def live_gui(tmp_path_factory) -> Iterator[LiveGui]:
    _require_environment()
    workdir = tmp_path_factory.mktemp("live_gui")
    profile = workdir / "profile"
    env = dict(os.environ, FREECAD_MCP_PROFILE_DIR=str(profile), PYTHONDONTWRITEBYTECODE="1")
    subprocess.run(
        [sys.executable, str(MCP_ROOT / "scripts" / "setup_isolated_profile.py")],
        cwd=MCP_ROOT, env=env, check=True, capture_output=True, timeout=120,
    )
    launcher_log = workdir / "freecad_output.log"
    freecad_log = workdir / "freecad.log"
    with launcher_log.open("w", encoding="utf-8") as output:
        launched = subprocess.run(
            [sys.executable, str(MCP_ROOT / "scripts" / "start_freecad_isolated.py"),
             "--log-file", str(freecad_log)],
            cwd=MCP_ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=600,
        )
    text = launcher_log.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"authenticated on \S+ \(pid=(\d+)", text)
    if launched.returncode != 0 or match is None:
        pytest.fail(f"FreeCAD GUI did not start:\n{text[-4000:]}")
    gui = LiveGui(int(match.group(1)), profile / "instance-manifest.json", workdir,
                  [launcher_log, freecad_log])
    try:
        yield gui
    finally:
        _stop(gui.pid)


@pytest.fixture(scope="session")
def mcp(live_gui: LiveGui) -> Iterator[McpClient]:
    client = McpClient(live_gui.manifest, live_gui.workdir)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def gui_log(live_gui: LiveGui) -> GuiLog:
    return GuiLog(live_gui.logs)
