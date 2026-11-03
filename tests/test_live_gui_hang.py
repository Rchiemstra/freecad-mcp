"""Hang detection without a FreeCAD GUI: fake client, fake process."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from scripts.start_freecad_isolated import _command_with_ptrace_permit
from tests.live_gui._hang import (
    FreeCadHung,
    HangMonitor,
    collect_native_backtraces,
    is_rpc_deadline,
)
from tests.live_gui._support import McpClient
from tests.live_gui.conftest import LiveGui, _LiveGuiSession

pytestmark = pytest.mark.unit

NODE = "tests/live_gui/test_live_gui_round12.py::test_current[Constraints[0]]"
PREVIOUS = "tests/live_gui/test_live_gui_round12.py::test_previous"
DEADLINE = "Authenticated RPC 'create_document' failed (TimeoutError)"


class _Process:
    def __init__(self, code: int | None = None) -> None:
        self.code = code

    def poll(self) -> int | None:
        return self.code


class _Client:
    def __init__(self, answered: bool) -> None:
        self.answered = answered
        self.freecad_hung = False
        self.probes = 0

    def probe_liveness(self, timeout: float = 5.0) -> bool:
        self.probes += 1
        return self.answered


def _bind(tmp_path, monkeypatch, *, answered: bool, alive: bool = True, stacks: str = "#0 sleep\n"):
    session = _LiveGuiSession(None)
    process = _Process(None if alive else 0)
    session.gui = LiveGui(4242, tmp_path / "manifest.json", tmp_path, [], process)
    client = _Client(answered)
    session.client = client
    session.current_nodeid = NODE
    session.last_passed_nodeid = PREVIOUS
    events: list[tuple] = []

    def collect(pid: int, timeout: float = 60.0) -> str:
        events.append(("gdb", pid, process.code))
        return stacks

    def stop(pid: int) -> None:
        events.append(("stop", pid))
        process.code = -15

    monkeypatch.setattr("tests.live_gui.conftest.collect_native_backtraces", collect)
    monkeypatch.setattr("tests.live_gui.conftest._stop", stop)
    restarted: list[str] = []
    session.close = lambda: restarted.append("close")  # type: ignore[method-assign]
    session.start = lambda: restarted.append("start") or setattr(process, "code", None)  # type: ignore[method-assign]
    return session, client, process, events, restarted


def _hit(session: _LiveGuiSession) -> None:
    session.observe_deadline(TimeoutError(DEADLINE), DEADLINE)


def test_deadline_markers_and_ordinary_errors():
    assert is_rpc_deadline(TimeoutError("client deadline"), "client deadline")
    assert is_rpc_deadline(None, "FreeCAD JSON-RPC response deadline exceeded")
    assert is_rpc_deadline(None, DEADLINE)
    assert is_rpc_deadline(
        None, "Timed out after 120.0s waiting for FreeCAD GUI response while executing"
    )
    assert is_rpc_deadline(None, "FreeCAD GUI is still executing a request that timed out")
    assert is_rpc_deadline(None, "GUI dispatch timed out after 60s")
    assert not is_rpc_deadline(None, "sketch constraint rejected")
    assert not is_rpc_deadline(ValueError("timed out locally"), "timed out locally")

    seen: list[str] = []
    client = McpClient.__new__(McpClient)
    client.observe_deadline = lambda exc, text: seen.append(text or "")
    client._notify_deadline(None, "sketch constraint rejected")
    client._notify_deadline(None, DEADLINE)
    assert seen == [DEADLINE]


def test_hang_detected_dumps_named_tests_and_restarts(tmp_path, monkeypatch, capfd):
    session, client, _process, events, restarted = _bind(tmp_path, monkeypatch, answered=False)
    with pytest.raises(FreeCadHung, match="FreeCAD stopped answering"):
        _hit(session)
    assert events == [("gdb", 4242, None), ("stop", 4242)]
    assert client.probes == 1
    assert client.freecad_hung is True
    report = (tmp_path / "freecad-hang.txt").read_text(encoding="utf-8")
    assert NODE in report
    assert PREVIOUS in report
    assert "#0 sleep" in report
    assert "FREECAD HUNG" in report
    err = capfd.readouterr().err
    assert "FREECAD HUNG" in err and NODE in err
    assert session.recover(NODE) is True
    assert restarted == ["close", "start"]
    assert session.abort_message is None


def test_hang_dump_bypasses_pytest_capture(tmp_path, monkeypatch):
    # pytest.exit in makereport drops the captured output of the test that
    # ends the session, so the second dump would never reach the step log.
    session, _client, _process, _events, _restarted = _bind(tmp_path, monkeypatch, answered=False)
    suspended: list[bool] = []
    written: list[bool] = []

    class _Capture:
        @contextmanager
        def global_and_fixture_disabled(self):
            suspended.append(True)
            try:
                yield
            finally:
                suspended.pop()

    session.capture = _Capture()
    monkeypatch.setattr(
        "tests.live_gui._hang._write_report", lambda *_a, **_k: written.append(bool(suspended)),
    )
    with pytest.raises(FreeCadHung):
        _hit(session)
    assert written == [True]
    assert suspended == []


def test_slow_call_with_a_live_probe_keeps_the_session(tmp_path, monkeypatch, capfd):
    session, client, process, events, restarted = _bind(tmp_path, monkeypatch, answered=True)
    _hit(session)
    assert client.probes == 1
    assert events == []
    assert process.code is None
    assert not (tmp_path / "freecad-hang.txt").exists()
    assert capfd.readouterr().err == ""
    assert session.recover(NODE) is False
    assert restarted == []


def test_gdb_missing_is_reported_and_still_fails_fast(tmp_path, monkeypatch, capfd):
    session, _client, _process, _events, restarted = _bind(tmp_path, monkeypatch, answered=False)
    monkeypatch.setattr("tests.live_gui._hang.shutil.which", lambda _name: None)
    monkeypatch.setattr(
        "tests.live_gui.conftest.collect_native_backtraces", collect_native_backtraces,
    )
    with pytest.raises(FreeCadHung, match="FreeCAD stopped answering"):
        _hit(session)
    report = (tmp_path / "freecad-hang.txt").read_text(encoding="utf-8")
    assert "Cannot collect native backtraces: gdb is not installed." in report
    assert "yama ptrace_scope=" in report
    assert session.recover(NODE) is True
    assert restarted == ["close", "start"]
    assert "gdb is not installed" in capfd.readouterr().err


def test_repeated_hangs_end_the_session(tmp_path, monkeypatch):
    session, client, process, events, restarted = _bind(tmp_path, monkeypatch, answered=False)
    with pytest.raises(FreeCadHung, match="FreeCAD stopped answering during"):
        _hit(session)
    assert session.recover(NODE) is True
    assert process.code is None
    client.freecad_hung = False
    with pytest.raises(FreeCadHung, match="ending the live GUI session"):
        _hit(session)
    assert session.recover(NODE) is False
    assert session.abort_message is not None
    assert "ending the live GUI session" in session.abort_message
    assert session.recover(NODE) is False
    assert restarted == ["close", "start"]
    assert events.count(("stop", 4242)) == 2


def test_dead_process_is_not_a_hang(tmp_path, monkeypatch, capfd):
    session, client, _process, events, _restarted = _bind(
        tmp_path, monkeypatch, answered=False, alive=False,
    )
    _hit(session)
    assert client.probes == 0
    assert events == []
    assert capfd.readouterr().err == ""


def test_monitor_does_not_dump_when_the_probe_answers(tmp_path):
    monitor = HangMonitor()
    collected: list[int] = []
    stopped: list[int] = []
    verdict = monitor.assess(
        poll=lambda: None,
        probe=lambda: True,
        pid=7,
        workdir=tmp_path,
        nodeid=NODE,
        last_passed=PREVIOUS,
        collect=lambda pid: collected.append(pid) or "",
        stop=lambda: stopped.append(1),
    )
    assert verdict.hung is False
    assert collected == []
    assert stopped == []
    assert not (tmp_path / "freecad-hang.txt").exists()


def test_gdb_attach_failure_includes_the_reason(monkeypatch):
    monkeypatch.setattr("tests.live_gui._hang.shutil.which", lambda _name: "/usr/bin/gdb")
    monkeypatch.setattr(
        "tests.live_gui._hang._run_gdb",
        lambda _args, _timeout: "ptrace: Operation not permitted\n",
    )
    text = collect_native_backtraces(1)
    assert "gdb could not attach to FreeCAD pid 1" in text
    assert "Operation not permitted" in text
    assert "ptrace_scope=" in text


def test_ptrace_permit_execs_freecad_in_place(monkeypatch):
    monkeypatch.delenv("FREECAD_MCP_PERMIT_PTRACE", raising=False)
    assert _command_with_ptrace_permit(["/build/bin/FreeCAD"]) == ["/build/bin/FreeCAD"]
    monkeypatch.setenv("FREECAD_MCP_PERMIT_PTRACE", "1")
    wrapped = _command_with_ptrace_permit(["/build/bin/FreeCAD"])
    assert wrapped[1] == "-c"
    assert "0x59616d61" in wrapped[2]
    assert wrapped[3:] == ["/build/bin/FreeCAD"]
