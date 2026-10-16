"""Exercise crash reporting and pytest recovery without launching FreeCAD."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]
pytestmark = pytest.mark.unit


@pytest.fixture
def process_factory():
    processes = []

    def start(code):
        process = subprocess.Popen([sys.executable, "-c", code])
        processes.append(process)
        return process

    yield start
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


@pytest.mark.parametrize("code, expected, name", [
    ("import os, signal; os.kill(os.getpid(), signal.SIGSEGV)", -11, "SIGSEGV"),
    ("pass", 0, "none"),
])
def test_death_reports_exact_status_and_restarts(
    tmp_path, process_factory, capfd, code, expected, name,
):
    from tests.live_gui._process import recover_if_dead

    process = process_factory(code)
    assert process.wait(timeout=5) == expected
    (tmp_path / "freecad_output.log").write_text("native crash detail\n")
    (tmp_path / "freecad.log").write_text("last operation\n")
    restarts = []
    assert recover_if_dead(process, tmp_path, "case[param]", lambda: restarts.append(1))
    assert restarts == [1]
    stderr = capfd.readouterr().err
    assert f"FREECAD DIED during case[param]: exit={expected} signal={name}\n" in stderr
    assert "native crash detail\n" in stderr
    assert "last operation\n" in stderr


def test_alive_process_is_untouched(tmp_path, process_factory, capfd):
    from tests.live_gui._process import recover_if_dead

    process = process_factory("import time; time.sleep(60)")
    assert not recover_if_dead(
        process, tmp_path, "healthy", lambda: pytest.fail("healthy process restarted"),
    )
    assert capfd.readouterr().err == ""


def test_tails_have_line_and_byte_limits(tmp_path, process_factory, capfd):
    from tests.live_gui._process import LOG_TAIL_BYTES, recover_if_dead, tail

    output = tmp_path / "freecad_output.log"
    native = tmp_path / "freecad.log"
    output.write_text("".join(f"output-{n}\n" for n in range(300)))
    native.write_text("".join(f"native-{n}\n" for n in range(200)))
    process = process_factory("pass")
    process.wait(timeout=5)
    recover_if_dead(process, tmp_path, "case", lambda: None)
    stderr = capfd.readouterr().err
    assert "output-99\n" not in stderr
    assert "output-100\n" in stderr and "output-299\n" in stderr
    assert "native-99\n" not in stderr
    assert "native-100\n" in stderr and "native-199\n" in stderr
    output.write_bytes(b"x" * (LOG_TAIL_BYTES * 4))
    assert len(tail(output, 200).encode()) <= LOG_TAIL_BYTES
    output.write_bytes(b"\xff" * (LOG_TAIL_BYTES * 4))
    assert len(tail(output, 200).encode()) <= LOG_TAIL_BYTES
    assert "unavailable" in tail(tmp_path / "missing.log", 100)
    output.write_bytes(b"\xff\nlast\n")
    assert tail(output, 200).endswith("last\n")


@pytest.mark.parametrize("code, expected", [
    ("import os, signal; os.kill(os.getpid(), signal.SIGSEGV)", -11),
    ("pass", 0),
])
def test_launcher_records_child_status(tmp_path, process_factory, code, expected):
    from scripts.start_freecad_isolated import _wait_for_exit
    from tests.live_gui._process import ProcessMonitor

    process = process_factory(code)
    status = tmp_path / "exit.json"
    _wait_for_exit(process, status)
    # The launcher itself exits successfully; the child's raw status must win.
    launcher = process_factory("pass")
    launcher.wait(timeout=5)
    assert ProcessMonitor(launcher, status).poll() == expected


def test_monitor_alive_and_lost_status(tmp_path, process_factory):
    from tests.live_gui._process import ProcessMonitor

    launcher = process_factory("import time; time.sleep(60)")
    monitor = ProcessMonitor(launcher, tmp_path / "exit.json")
    assert monitor.poll() is None
    monitor.status_file.write_text('{"returncode": null}')
    assert monitor.poll() is None
    launcher.kill()
    launcher.wait(timeout=5)
    with pytest.raises(RuntimeError, match="launcher.*without.*exit status"):
        monitor.poll()


def test_monitor_waits_for_status_publication(tmp_path, process_factory):
    from tests.live_gui._process import ProcessMonitor

    if not hasattr(os, "pidfd_open"):
        pytest.skip("Linux pidfd required")
    child = process_factory("pass")
    monitor = ProcessMonitor(None, tmp_path / "exit.json", child.pid)
    child.wait(timeout=5)
    # Publish deliberately after death; poll must wait for the real status.
    launcher = process_factory(
        "import time; from pathlib import Path; time.sleep(0.1); "
        f"Path({str(tmp_path / 'exit.json')!r}).write_text('{{\"returncode\": 0}}')"
    )
    monitor.launcher = launcher
    try:
        assert monitor.poll() == 0
    finally:
        monitor.close()


@pytest.mark.parametrize("args", [
    ["--exit-status-file", "exit.json", "--log-file", "native.log"],
    ["--exit-status-file=exit.json", "--log-file", "native.log"],
])
def test_launcher_consumes_status_path(args):
    from scripts.start_freecad_isolated import _consume_exit_status_file

    path, remaining = _consume_exit_status_file(args)
    assert path == Path("exit.json")
    assert remaining == ["--log-file", "native.log"]


@pytest.mark.parametrize("phase", ["call", "setup", "teardown", "silent", "timeout"])
@pytest.mark.parametrize("restart_fails", [False, True])
def test_pytest_reports_and_recovers(pytester, monkeypatch, phase, restart_fails):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(root), str(root / "src"))))
    events = pytester.path / "events"
    pytester.makeconftest(f'''
import signal
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
import pytest
from tests.live_gui import conftest as live

for name in ('live_gui', 'mcp', 'gui_log', '_live_gui_session', 'pytest_runtest_makereport'):
    if hasattr(live, name):
        globals()[name] = getattr(live, name)

def record(text):
    with Path({str(events)!r}).open('a') as stream:
        stream.write(text + '\\n')

starts = 0
@contextmanager
def launch(factory):
    global starts
    starts += 1
    record('start ' + str(starts))
    if starts == 2 and {restart_fails!r}:
        pytest.fail('fake restart rejected')
    workdir = factory.mktemp('fake_gui')
    (workdir / 'freecad_output.log').write_text('crash output\\n')
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    gui = live.LiveGui(process.pid, workdir / 'manifest', workdir,
                       [workdir / 'freecad_output.log', workdir / 'freecad.log'])
    gui.process = process
    try:
        yield gui
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        record('stop ' + str(starts))
live._launch_live_gui = launch

class Client:
    gui_request_timed_out = False
    def __init__(self, *args): pass
    def close(self): record('close')
live.McpClient = Client

def die(session):
    import os
    os.kill(session.gui.pid, signal.SIGSEGV)
    session.gui.process.wait(timeout=5)

@pytest.fixture
def scenario(mcp, _live_gui_session):
    if {phase!r} == 'setup':
        die(_live_gui_session)
        raise ConnectionRefusedError('during setup')
    yield
    if {phase!r} == 'teardown':
        die(_live_gui_session)
        raise ConnectionRefusedError('during teardown')
''')
    pytester.makepyfile(f'''
import pytest
from conftest import die

def test_01_crash(scenario, mcp, _live_gui_session):
    if {phase!r} not in ('setup', 'teardown'):
        die(_live_gui_session)
        if {phase!r} == 'timeout':
            mcp.gui_request_timed_out = True
        if {phase!r} != 'silent':
            raise ConnectionRefusedError('connection refused')

def test_02_next(live_gui):
    assert live_gui.process.poll() is None

def test_03_reuse(live_gui):
    assert live_gui.process.poll() is None
''')
    result = pytester.runpytest_subprocess("-q", "-p", "no:cacheprovider")
    diagnostic = "FREECAD DIED during test_pytest_reports_and_recovers.py::test_01_crash: exit=-11 signal=SIGSEGV"
    assert diagnostic in result.stderr.str()
    assert result.stderr.str().count("FREECAD DIED") == 1
    if restart_fails:
        assert result.ret == 2
        assert "FreeCAD restart failed" in result.stdout.str() + result.stderr.str()
        assert "test_02_next" not in result.stdout.str()
    else:
        if phase in ("setup", "teardown"):
            result.assert_outcomes(passed=2 if phase == "setup" else 3, errors=1)
        else:
            result.assert_outcomes(passed=2, failed=1)
        assert events.read_text().splitlines() == [
            "start 1", "close", "stop 1", "start 2", "close", "stop 2",
        ]
