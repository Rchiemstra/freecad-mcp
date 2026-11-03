"""Launch a real FreeCAD GUI with the MCP addon and drive it through the MCP server.

Requirements (the tests skip without them):

* ``FREECAD_MCP_ISOLATED_FREECAD``: absolute path of a FreeCAD GUI executable.
* ``DISPLAY``: an X server, e.g. ``xvfb-run -a`` or ``Xvfb :99``.

Everything FreeCAD prints (Report view errors, Coin and Qt warnings) is captured
and every test fails on new warning or error lines unless it allows them.
"""

from __future__ import annotations

import json
import os
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

from freecad_mcp.startup_progress import DEFAULT_RPC_WAIT_TIMEOUT
from tests.live_gui._hang import (
    PROBE_TIMEOUT_SECONDS,
    FreeCadHung,
    HangMonitor,
    collect_native_backtraces,
    is_rpc_deadline,
)
from tests.live_gui._process import ProcessMonitor, recover_if_dead, tail
from tests.live_gui._support import MCP_ROOT, GuiLog, McpClient, close_documents

_TEST_FAILED = pytest.StashKey[bool]()


@dataclass
class LiveGui:
    pid: int
    manifest: Path
    workdir: Path
    logs: list[Path]
    process: ProcessMonitor | None = None


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
    env = dict(
        os.environ,
        FREECAD_MCP_PROFILE_DIR=str(profile),
        PYTHONDONTWRITEBYTECODE="1",
        # See start_freecad_isolated._command_with_ptrace_permit. Set on the
        # launcher, which is the process that forks FreeCAD.
        FREECAD_MCP_PERMIT_PTRACE="1",
    )
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
    exit_status = workdir / "freecad_exit.json"
    launcher = [sys.executable, "-u", str(MCP_ROOT / "scripts" / "start_freecad_isolated.py"),
                "--exit-status-file", str(exit_status),
                "--log-file", str(freecad_log)]
    if sys.platform.startswith("linux"):
        # FreeCAD's C stdout can retain messages across several tests, even
        # with PYTHONUNBUFFERED. Apply line buffering to the launcher and its
        # children so an expected worker failure cannot arrive in a later
        # test's log window. The native log and stderr remain checked too.
        launcher = ["stdbuf", "-oL", *launcher]
    with launcher_log.open("w", encoding="utf-8") as output:
        launched = subprocess.Popen(
            launcher,
            cwd=MCP_ROOT, env=env, stdout=output, stderr=subprocess.STDOUT,
        )
    gui = None
    try:
        # The launcher owns readiness budgets; retain a backstop if it hangs.
        deadline = time.monotonic() + DEFAULT_RPC_WAIT_TIMEOUT + 120
        while True:
            # The launcher publishes this only after proving RPC identity and
            # closing its readiness connection. Logs may be arbitrarily noisy.
            if exit_status.is_file():
                pid = int(json.loads(exit_status.read_text())["pid"])
                break
            if launched.poll() is not None or time.monotonic() >= deadline:
                text = tail(launcher_log, 200)
                pytest.fail(f"FreeCAD GUI did not start:\n{text[-4000:]}")
            time.sleep(0.2)
        gui = LiveGui(pid, profile / "instance-manifest.json", workdir,
                      [launcher_log, freecad_log], ProcessMonitor(launched, exit_status, pid))
        yield gui
    finally:
        try:
            if gui is not None:
                try:
                    exited = gui.process.poll() is not None
                except (OSError, ValueError, RuntimeError):
                    exited = False
                if not exited:
                    _stop(gui.pid)
        finally:
            if gui is not None:
                gui.process.close()
            try:
                launched.wait(timeout=10)
            except subprocess.TimeoutExpired:
                launched.terminate()
                try:
                    launched.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    launched.kill()
                    launched.wait(timeout=5)


class _LiveGuiSession:
    """Reuse healthy processes, but retire uncertain work after its scenario."""

    def __init__(self, tmp_path_factory):
        self.tmp_path_factory = tmp_path_factory
        self.stack = ExitStack()
        self.gui: LiveGui | None = None
        self.client: McpClient | None = None
        self.abort_message: str | None = None
        self.current_nodeid: str | None = None
        self.last_passed_nodeid: str | None = None
        self.hang_message: str | None = None
        self.hang_action: str = "none"
        self.hang_pending = False
        self.hung_nodeid: str | None = None
        self.session_finished = False
        self.hang_monitor = HangMonitor()

    def start(self) -> None:
        if self.gui is not None:
            return
        with ExitStack() as stack:
            gui = stack.enter_context(_launch_live_gui(self.tmp_path_factory))
            client = McpClient(gui.manifest, gui.workdir)
            client.observe_deadline = self.observe_deadline
            stack.callback(client.close)
            self.stack = stack.pop_all()
            self.gui, self.client = gui, client

    def close(self) -> None:
        try:
            self.stack.close()
        finally:
            self.gui = None
            self.client = None

    def _restart(self, nodeid: str) -> None:
        try:
            self.close()
            self.start()
        except (Exception, pytest.fail.Exception, pytest.skip.Exception) as exc:
            # Fixture teardown can combine pytest.exit with another error
            # into an ExceptionGroup. Exit from makereport instead.
            self.abort_message = f"FreeCAD restart failed after {nodeid}: {exc}"

    def observe_deadline(self, exc: BaseException | None, text: str | None) -> None:
        """Probe after an RPC deadline. Raise when FreeCAD has stopped answering."""
        if self.client is not None and getattr(self.client, "freecad_hung", False):
            raise FreeCadHung(self.hang_message or "FreeCAD stopped answering")
        if not is_rpc_deadline(exc, text):
            return
        gui = self.gui
        if gui is None or gui.process is None:
            return
        try:
            verdict = self.hang_monitor.assess(
                poll=gui.process.poll,
                probe=self._probe,
                pid=gui.pid,
                workdir=gui.workdir,
                nodeid=self.current_nodeid or "the live GUI session",
                last_passed=self.last_passed_nodeid,
                collect=collect_native_backtraces,
                stop=lambda: _stop(gui.pid),
                trigger=text or ("" if exc is None else str(exc)),
            )
        except (OSError, ValueError, RuntimeError) as monitor_error:
            self.abort_message = (
                f"FreeCAD process monitoring failed during "
                f"{self.current_nodeid or 'the live GUI session'}: {monitor_error}"
            )
            return
        if not verdict.hung:
            return
        self.hang_message = verdict.message
        self.hang_action = verdict.action
        self.hang_pending = True
        self.hung_nodeid = self.current_nodeid
        if self.client is not None:
            self.client.freecad_hung = True
        raise FreeCadHung(verdict.message)

    def _probe(self) -> bool:
        client = self.client
        probe = getattr(client, "probe_liveness", None)
        if not callable(probe):
            return False
        try:
            return bool(probe(PROBE_TIMEOUT_SECONDS))
        except Exception:
            return False

    def recover(self, nodeid: str) -> bool:
        if self.session_finished:
            return False
        if self.hang_pending:
            self.hang_pending = False
            if self.hang_action == "exit":
                self.abort_message = self.hang_message or (
                    f"FreeCAD stopped answering again during {nodeid}; "
                    "ending the live GUI session"
                )
                self.session_finished = True
                return False
            # First hang: dump already happened and the process was killed.
            # A fresh GUI lets the rest of the suite run. The next hang exits.
            self._restart(nodeid)
            return True
        if self.gui is None or self.gui.process is None:
            return False
        try:
            return recover_if_dead(
                self.gui.process, self.gui.workdir, nodeid, lambda: self._restart(nodeid),
            )
        except (OSError, ValueError, RuntimeError) as exc:
            self.abort_message = f"FreeCAD process monitoring failed during {nodeid}: {exc}"
            return False


def _check_for_death(session, item) -> bool:
    # sys.__stderr__ alone still points into pytest's fd capture. Suspend it
    # here so diagnostics are printed even for setup/teardown failures in CI.
    capture = item.config.pluginmanager.getplugin("capturemanager")
    with capture.global_and_fixture_disabled():
        return session.recover(item.nodeid)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    report = yield
    session = item.funcargs.get("_live_gui_session")
    if session is not None:
        died = _check_for_death(session, item)
        if session.abort_message:
            pytest.exit(session.abort_message, returncode=2)
        # Fakes used by fixture tests only carry the fields they need.
        hung_node = getattr(session, "hung_nodeid", None)
        if hung_node == item.nodeid and report.when == "call" and report.passed:
            report.outcome = "failed"
            report.longrepr = session.hang_message
        elif died and report.passed:
            report.outcome = "failed"
            report.longrepr = (
                f"FreeCAD died during {item.nodeid} ({report.when}); see stderr diagnostics"
            )
        if report.when == "call" and report.passed:
            session.last_passed_nodeid = item.nodeid
        if hung_node == item.nodeid and report.when == "call":
            session.hung_nodeid = None
    if report.failed:
        item.stash[_TEST_FAILED] = True
    return report


@pytest.fixture(scope="session")
def _live_gui_session(tmp_path_factory) -> Iterator[_LiveGuiSession]:
    session = _LiveGuiSession(tmp_path_factory)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def live_gui(_live_gui_session, request) -> Iterator[LiveGui]:
    _live_gui_session.current_nodeid = request.node.nodeid
    _live_gui_session.start()
    assert _live_gui_session.gui is not None
    try:
        yield _live_gui_session.gui
    finally:
        # Run before the session finalizer stops the process, including on
        # the last test and when another fixture fails during teardown.
        if _check_for_death(_live_gui_session, request.node):
            pytest.fail("FreeCAD died during teardown; see stderr diagnostics")


@pytest.fixture
def mcp(live_gui: LiveGui, _live_gui_session, request) -> Iterator[McpClient]:
    client = _live_gui_session.client
    assert client is not None
    failed = False
    try:
        yield client
    except BaseException:
        failed = True
        raise
    finally:
        # Ordinary assertion/setup failures keep the same healthy GUI session.
        # Clean every leftover, even when the scenario missed its own finally.
        try:
            if (
                (failed or request.node.stash.get(_TEST_FAILED, False))
                and _live_gui_session.client is client
                and not client.gui_request_timed_out
            ):
                if not _check_for_death(_live_gui_session, request.node):
                    close_documents(client)
        finally:
            _retire_timed_out_client(client, _live_gui_session, request)


def _retire_timed_out_client(client, session, request) -> None:
    # Keep the offending result/failure intact. A fresh profile and MCP
    # connection on the next test prevent timeout occupancy, leases, or
    # delayed log lines from contaminating unrelated scenarios.
    if client.gui_request_timed_out and session.client is client:
        if _check_for_death(session, request.node):
            pytest.fail("FreeCAD died during teardown; see stderr diagnostics")
        session.close()


@pytest.fixture
def gui_log(live_gui: LiveGui) -> GuiLog:
    return GuiLog(live_gui.logs)
