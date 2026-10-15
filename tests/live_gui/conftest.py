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
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
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


@pytest.fixture(scope="session")
def freecad_source_root() -> Path:
    """Use the CI checkout override or the repo containing this MCP submodule."""
    override = os.environ.get("CI_WORKSPACE")
    root = (Path(override) if override else MCP_ROOT.parents[2]).resolve()
    if not (root / "src" / "Mod").is_dir():
        pytest.fail(f"FreeCAD source tree not found at {root}")
    return root


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


@contextmanager
def _launch_live_gui(tmp_path_factory) -> Iterator[LiveGui]:
    _require_environment()
    workdir = tmp_path_factory.mktemp("live_gui")
    profile = workdir / "profile"
    env = dict(os.environ, FREECAD_MCP_PROFILE_DIR=str(profile), PYTHONDONTWRITEBYTECODE="1")
    # The launcher's strict endpoint reservation also rejects an old socket
    # in TIME_WAIT. Each replacement profile needs its own unused endpoint.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    subprocess.run(
        [sys.executable, str(MCP_ROOT / "scripts" / "setup_isolated_profile.py"),
         "--port", str(port)],
        cwd=MCP_ROOT, env=env, check=True, capture_output=True, timeout=120,
    )
    launcher_log = workdir / "freecad_output.log"
    freecad_log = workdir / "freecad.log"
    launcher = [sys.executable, str(MCP_ROOT / "scripts" / "start_freecad_isolated.py"),
                "--log-file", str(freecad_log)]
    if sys.platform.startswith("linux"):
        # FreeCAD's C stdout can retain messages across several tests, even
        # with PYTHONUNBUFFERED. Apply line buffering to the launcher and its
        # children so an expected worker failure cannot arrive in a later
        # test's log window. The native log and stderr remain checked too.
        launcher = ["stdbuf", "-oL", *launcher]
    with launcher_log.open("w", encoding="utf-8") as output:
        launched = subprocess.run(
            launcher,
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


class _LiveGuiSession:
    """Reuse healthy processes, but retire uncertain work after its scenario."""

    def __init__(self, tmp_path_factory):
        self.tmp_path_factory = tmp_path_factory
        self.stack = ExitStack()
        self.gui: LiveGui | None = None
        self.client: McpClient | None = None

    def start(self) -> None:
        if self.gui is not None:
            return
        with ExitStack() as stack:
            gui = stack.enter_context(_launch_live_gui(self.tmp_path_factory))
            client = McpClient(gui.manifest, gui.workdir)
            stack.callback(client.close)
            self.stack = stack.pop_all()
            self.gui, self.client = gui, client

    def close(self) -> None:
        try:
            self.stack.close()
        finally:
            self.gui = None
            self.client = None


@pytest.fixture(scope="session")
def _live_gui_session(tmp_path_factory) -> Iterator[_LiveGuiSession]:
    session = _LiveGuiSession(tmp_path_factory)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def live_gui(_live_gui_session) -> LiveGui:
    _live_gui_session.start()
    assert _live_gui_session.gui is not None
    return _live_gui_session.gui


@pytest.fixture
def mcp(live_gui: LiveGui, _live_gui_session) -> Iterator[McpClient]:
    client = _live_gui_session.client
    assert client is not None
    try:
        yield client
    finally:
        # Keep the offending result/failure intact. A fresh profile and MCP
        # connection on the next test prevent timeout occupancy, leases, or
        # delayed log lines from contaminating unrelated scenarios.
        if client.gui_request_timed_out:
            _live_gui_session.close()


@pytest.fixture
def gui_log(live_gui: LiveGui) -> GuiLog:
    return GuiLog(live_gui.logs)
