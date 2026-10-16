"""A failed live request must not poison the next pytest scenario."""

import os
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]
pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", ["executing", "busy", "transport", "parallel"])
def test_timeout_fails_only_its_scenario(pytester, monkeypatch, failure):
    # Exercise the real fixtures and client timeout tracking, replacing only
    # the process/transport boundary. No GUI or two-minute sleep is needed.
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(root), str(root / "src"))))
    events = pytester.path / "events.txt"
    pytester.makeconftest(
        f"""
import asyncio
import json
import socket
from pathlib import Path
from types import SimpleNamespace
from tests.live_gui import conftest as live
from tests.live_gui._support import McpClient, ToolResult

for name in ('live_gui', 'mcp', 'gui_log', '_live_gui_session', 'pytest_runtest_makereport'):
    if hasattr(live, name):
        globals()[name] = getattr(live, name)

starts = []
ports = set()
reservations = []
port = 9876
def record(event):
    with Path({str(events)!r}).open('a') as output:
        output.write(event + '\\n')

live._require_environment = lambda: Path('/fake/FreeCAD')
def run(command, **kwargs):
    global port
    if '--port' in command:
        port = int(command[command.index('--port') + 1])
    if '--log-file' in command:
        # The isolated launcher reserves with SO_REUSEADDR disabled. Even a
        # stopped GUI's old endpoint can remain unavailable during TIME_WAIT.
        assert port not in ports, 'restart reused an unavailable endpoint'
        ports.add(port)
        reservation = socket.socket()
        reservation.bind(('127.0.0.1', port))
        reservations.append(reservation)
        pid = 100 + len(starts)
        starts.append(pid)
        kwargs['stdout'].write(f'authenticated on loopback (pid={{pid}})')
        kwargs['stdout'].flush()
        status = Path(command[command.index('--exit-status-file') + 1])
        status.write_text(json.dumps({{'pid': pid, 'returncode': None}}))
        record(f'start {{pid}}')
    return SimpleNamespace(returncode=0)
live.subprocess.run = run
def popen(command, **kwargs):
    run(command, **kwargs)
    return SimpleNamespace(poll=lambda: None, wait=lambda **kwargs: 0)
live.subprocess.Popen = popen
live.ProcessMonitor = lambda *args: SimpleNamespace(poll=lambda: None, close=lambda: None)
live._stop = lambda pid: record(f'stop {{pid}}')

class Client(McpClient):
    def __init__(self, manifest, workdir):
        self.pid = starts[-1]
        self.gui_request_timed_out = False
        self.poisoned = False

    def _run(self, coroutine, **kwargs):
        return asyncio.run(coroutine)

    async def _call(self, tool, args):
        if tool == 'rejected':
            return ToolResult(tool, True, 'Expected model validation rejection', {{}})
        if tool == 'poison':
            self.poisoned = True
            if {failure!r} == 'transport':
                raise TimeoutError('client deadline')
            text = ('FreeCAD GUI is still executing a request that timed out'
                    if {failure!r} == 'busy' else
                    'Timed out after 120.0s waiting for FreeCAD GUI response while executing; '
                    'execution continues in FreeCAD')
            return ToolResult(tool, True, text, {{}})
        if self.poisoned:
            return ToolResult(tool, True, 'GUI remains occupied', {{}})
        return ToolResult(tool, False, str(self.pid), {{}})

    def close(self):
        record(f'close {{self.pid}}')

live.McpClient = Client
"""
    )
    pytester.makepyfile(
        f"""
def test_00_expected_rejection(mcp):
    assert mcp.call('rejected').is_error

def test_00_healthy_after_rejection(mcp, live_gui):
    assert mcp.call('read').text == '100'
    assert live_gui.pid == 100

def test_01_offender(mcp):
    if {failure!r} == 'parallel':
        result = mcp.parallel([('poison', {{}})])[0]
    else:
        result = mcp.call('poison')
    assert result.ok, result.text

def test_02_next_scenario(mcp, live_gui, gui_log):
    result = mcp.call('read')
    assert result.ok, result.text
    assert result.text == '101'
    assert live_gui.pid == 101
    assert live_gui.workdir.name != 'live_gui0'
    assert not gui_log.problems()

def test_03_healthy_session_is_reused(mcp, live_gui):
    assert mcp.call('read').text == '101'
    assert live_gui.pid == 101
"""
    )
    result = pytester.runpytest_subprocess("-q", "-p", "no:cacheprovider")
    result.assert_outcomes(failed=1, passed=4)
    assert events.read_text().splitlines() == [
        "start 100", "close 100", "stop 100",
        "start 101", "close 101", "stop 101",
    ]
