"""Deterministic startup watchdog tests: elapsed time never sleeps."""

from pathlib import Path

import pytest

from freecad_mcp.startup_progress import STARTUP_PROGRESS_ENV, record_startup_phase
from tests.isolated.test_isolated_scripts import _load_script


def _watchdog(tmp_path, *, probe=lambda _pid: (None, None), cap=900):
    launcher = _load_script("start_freecad_isolated.py")
    clock = [0.0]
    watchdog = launcher._StartupWatchdog(
        123, tmp_path, stall_timeout=60, wait_timeout=cap,
        clock=lambda: clock[0], probe=probe,
    )
    return watchdog, clock


@pytest.mark.parametrize("source", ["cpu", "read_bytes"])
def test_slow_start_keeps_progressing_past_sixty_seconds(tmp_path, source):
    counters = [0.0, 0]
    watchdog, clock = _watchdog(tmp_path, probe=lambda _pid: tuple(counters))
    for elapsed in (0, 30, 60, 90, 120):
        clock[0] = elapsed
        counters[source == "read_bytes"] = elapsed * (1024 * 1024 if source == "read_bytes" else 1)
        assert watchdog.sample() is None
    assert watchdog.clock() - watchdog.started == 120


def test_stall_reports_phase_and_counters_at_sixty_seconds(tmp_path):
    watchdog, clock = _watchdog(tmp_path, probe=lambda _pid: (2.5, 4096))
    (tmp_path / "gui-ready").touch()
    assert watchdog.sample() is None
    clock[0] = 59.9
    assert watchdog.sample() is None
    clock[0] = 60
    assert watchdog.sample() == "no-progress timeout"
    message = watchdog.describe()
    for detail in ("phase=gui-ready", "idle=60.0s", "cpu_seconds=2.50",
                   "read_bytes=4096", "sources=cpu,phases,read_bytes"):
        assert detail in message


def test_cap_wins_even_with_continuing_progress(tmp_path):
    counters = [0.0, 0]
    watchdog, clock = _watchdog(tmp_path, probe=lambda _pid: tuple(counters), cap=90)
    for elapsed in (0, 30, 60):
        clock[0] = counters[0] = elapsed
        assert watchdog.sample() is None
    clock[0] = counters[0] = 90
    assert watchdog.sample() == "absolute cap reached"


def test_phase_only_progress_extends_stall_but_rewrites_do_not(tmp_path):
    watchdog, clock = _watchdog(tmp_path)
    assert watchdog.sample() is None
    for elapsed, phase in ((50, "addon-imported"), (100, "gui-ready"),
                           (150, "rpc-listening")):
        clock[0] = elapsed
        (tmp_path / phase).touch()
        assert watchdog.sample() is None
    clock[0] = 209
    (tmp_path / "gui-ready").touch()  # No regression/rewrite heartbeat.
    assert watchdog.sample() is None
    clock[0] = 210
    assert watchdog.sample() == "no-progress timeout"
    assert "phase=rpc-listening" in watchdog.describe()
    assert "sources=phases" in watchdog.describe()


def test_unavailable_probe_still_obeys_cap_with_phase_progress(tmp_path):
    watchdog, clock = _watchdog(tmp_path, cap=90)
    assert watchdog.sample() is None
    clock[0] = 50
    (tmp_path / "addon-imported").touch()
    assert watchdog.sample() is None
    clock[0] = 90
    (tmp_path / "gui-ready").touch()
    assert watchdog.sample() == "absolute cap reached"
    assert "cpu_seconds=unavailable; read_bytes=unavailable" in watchdog.describe()
    assert "sources=phases" in watchdog.describe()


def test_no_sources_still_times_out(tmp_path):
    watchdog, clock = _watchdog(tmp_path / "absent")
    assert watchdog.sample() is None
    clock[0] = 60
    assert watchdog.sample() == "no-progress timeout"
    assert "sources=none" in watchdog.describe()


def test_counter_disappearance_or_regression_does_not_count(tmp_path):
    counters = [5.0, 100]
    watchdog, clock = _watchdog(tmp_path, probe=lambda _pid: tuple(counters))
    assert watchdog.sample() is None
    clock[0] = 30
    counters[:] = [None, None]
    assert watchdog.sample() is None
    assert "sources=phases" in watchdog.describe()
    clock[0] = 60
    counters[:] = [4.0, 90]
    assert watchdog.sample() == "no-progress timeout"
    assert "cpu_seconds=5.00; read_bytes=100" in watchdog.describe()


def test_idle_ticks_below_minimum_do_not_extend_stall(tmp_path):
    counters = [10.0, 2 * 1024 * 1024]
    watchdog, clock = _watchdog(tmp_path, probe=lambda _pid: tuple(counters))
    assert watchdog.sample() is None
    for elapsed in range(1, 61):
        clock[0] = elapsed
        counters[0] += 0.025  # Measured idle GUI rate, rounded up.
        counters[1] += 1024
        assert watchdog.sample() == ("no-progress timeout" if elapsed == 60 else None)


def test_cpu_minimum_accumulates_since_progress_mark(tmp_path):
    counters = [0.0, None]
    watchdog, clock = _watchdog(tmp_path, probe=lambda _pid: tuple(counters))
    for elapsed in range(0, 121):
        clock[0] = elapsed
        counters[0] = elapsed * 0.2
        assert watchdog.sample() is None


def test_rpc_listening_ignores_polling_cpu_and_io(tmp_path):
    counters = [0.0, 0]
    watchdog, clock = _watchdog(tmp_path, probe=lambda _pid: tuple(counters))
    assert watchdog.sample() is None
    clock[0] = 30
    (tmp_path / "rpc-listening").touch()
    assert watchdog.sample() is None
    for elapsed in range(31, 91):
        clock[0] = elapsed
        counters[:] = [elapsed, elapsed * 1024 * 1024]
        assert watchdog.sample() == ("no-progress timeout" if elapsed == 90 else None)
    assert "sources=phases" in watchdog.describe()


def test_reporting_after_proof_only_updates_phases_even_past_cap(tmp_path):
    watchdog, clock = _watchdog(tmp_path, cap=90)
    assert watchdog.sample() is None
    clock[0] = 91
    (tmp_path / "rpc-listening").touch()
    assert watchdog.sample(report_only=True) is None
    assert watchdog.phases == ["rpc-listening@91.0s"]
    assert watchdog.last_progress == 0


def test_raising_probe_omits_resource_sources_and_still_times_out(tmp_path):
    def broken_probe(_pid):
        raise RuntimeError("optional probe failed")

    watchdog, clock = _watchdog(tmp_path, probe=broken_probe)
    assert watchdog.sample() is None
    clock[0] = 60
    assert watchdog.sample() == "no-progress timeout"
    assert "cpu_seconds=unavailable; read_bytes=unavailable; sources=phases" in watchdog.describe()


def test_live_fixture_bounds_a_hung_launcher_by_cap_plus_margin(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from tests.live_gui import conftest as live

    launcher = _load_script("start_freecad_isolated.py")
    assert live.DEFAULT_RPC_WAIT_TIMEOUT == launcher.DEFAULT_RPC_WAIT_TIMEOUT
    clock = [0.0]
    waited = []

    def sleep(_seconds):
        clock[0] += 1

    process = SimpleNamespace(poll=lambda: None, wait=lambda **kw: waited.append(kw))
    monkeypatch.setattr(live, "_require_environment", lambda: None)
    monkeypatch.setattr(live, "DEFAULT_RPC_WAIT_TIMEOUT", 3)
    monkeypatch.setattr(live, "time", SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep))
    monkeypatch.setattr(live, "subprocess", SimpleNamespace(
        run=lambda *_args, **_kw: None, Popen=lambda *_args, **_kw: process,
        STDOUT=live.subprocess.STDOUT,
    ))
    factory = SimpleNamespace(mktemp=lambda _name: tmp_path)
    with pytest.raises(pytest.fail.Exception, match="FreeCAD GUI did not start"):
        with live._launch_live_gui(factory):
            pytest.fail("hung launcher was accepted")
    assert clock[0] == 123
    assert waited == [{"timeout": 10}]


def test_marker_writes_only_when_launcher_opted_in(tmp_path, monkeypatch):
    monkeypatch.delenv(STARTUP_PROGRESS_ENV, raising=False)
    record_startup_phase("addon-imported")
    assert not list(tmp_path.iterdir())
    monkeypatch.setenv(STARTUP_PROGRESS_ENV, str(tmp_path))
    record_startup_phase("addon-imported")
    assert (tmp_path / "addon-imported").is_file()
    record_startup_phase("unknown")
    assert len(list(tmp_path.iterdir())) == 1
    monkeypatch.setenv(STARTUP_PROGRESS_ENV, str(tmp_path / "missing"))
    record_startup_phase("gui-ready")  # A hint failure cannot break FreeCAD.


@pytest.mark.parametrize("option, expected", [
    ([], 60.0), (["--rpc-stall-timeout", "120"], 120.0),
    (["--rpc-stall-timeout=0.5"], 0.5),
])
def test_stall_timeout_parsing(option, expected):
    launcher = _load_script("start_freecad_isolated.py")
    timeout, rest = launcher._consume_rpc_stall_timeout([*option, "--", "macro"])
    assert timeout == expected
    assert rest == ["--", "macro"]


@pytest.mark.parametrize("value", ["", "bad", "0", "-1", "nan", "inf", "-inf"])
def test_invalid_stall_timeout(value):
    launcher = _load_script("start_freecad_isolated.py")
    with pytest.raises(SystemExit, match="--rpc-stall-timeout requires"):
        launcher._consume_rpc_stall_timeout(["--rpc-stall-timeout=" + value])


def test_missing_or_duplicate_stall_timeout():
    launcher = _load_script("start_freecad_isolated.py")
    for args in (["--rpc-stall-timeout"],
                 ["--rpc-stall-timeout=60", "--rpc-stall-timeout=90"]):
        with pytest.raises(SystemExit, match="--rpc-stall-timeout requires"):
            launcher._consume_rpc_stall_timeout(args)


def test_linux_probe_parses_comm_with_spaces_and_reads_independently(monkeypatch):
    launcher = _load_script("start_freecad_isolated.py")
    # Fields 3..13, then utime/stime (14/15).
    stat = "123 (Free CAD) worker) " + " ".join(["0"] * 11 + ["125", "75"])
    monkeypatch.setattr(Path, "read_text", lambda path: (
        stat if path.name == "stat" else "rchar: 9000\nread_bytes: 4096\n"
    ))
    monkeypatch.setattr(launcher.os, "sysconf", lambda _name: 100)
    assert launcher._linux_process_progress(123) == (2.0, 4096)

    def partial_read(path):
        if path.name == "stat":
            raise PermissionError("denied")
        return "read_bytes: 4096\n"

    monkeypatch.setattr(Path, "read_text", partial_read)
    assert launcher._linux_process_progress(123) == (None, 4096)
    monkeypatch.setattr(Path, "read_text", lambda _path: "unreadable")
    assert launcher._linux_process_progress(123) == (None, None)


def test_other_platform_has_no_cheap_process_probe(monkeypatch):
    launcher = _load_script("start_freecad_isolated.py")
    monkeypatch.setattr(launcher.sys, "platform", "other")
    assert launcher._process_progress(123) == (None, None)


@pytest.mark.parametrize("operation", ["WinDLL", "_query_windows_process_progress"])
def test_windows_probe_setup_or_calls_can_raise(monkeypatch, operation):
    import ctypes

    launcher = _load_script("start_freecad_isolated.py")

    def broken(*_args, **_kwargs):
        raise RuntimeError("ctypes unavailable")

    target = ctypes if operation == "WinDLL" else launcher
    monkeypatch.setattr(target, operation, broken, raising=False)
    assert launcher._windows_process_progress(123) == (None, None)


@pytest.mark.parametrize("times_ok, io_ok, opened", [
    (True, True, True), (False, True, True), (True, False, True),
    (False, False, False),
])
def test_windows_probe_counters_are_independent_and_handle_is_closed(
    monkeypatch, times_ok, io_ok, opened,
):
    import ctypes
    from types import SimpleNamespace

    launcher = _load_script("start_freecad_isolated.py")
    closed = []

    class Function:
        def __init__(self, call):
            self.call = call

        def __call__(self, *args):
            return self.call(*args)

    def times(_handle, _created, _exited, kernel, user):
        kernel._obj.dwLowDateTime = 10_000_000
        user._obj.dwLowDateTime = 20_000_000
        return times_ok

    def io(_handle, counters):
        counters._obj.ReadTransferCount = 8192
        return io_ok

    api = SimpleNamespace(
        OpenProcess=Function(lambda *_args: 123 if opened else None),
        CloseHandle=Function(lambda handle: closed.append(handle)),
        GetProcessTimes=Function(times), GetProcessIoCounters=Function(io),
    )
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kw: api, raising=False)
    assert launcher._windows_process_progress(123) == (
        3.0 if opened and times_ok else None,
        8192 if opened and io_ok else None,
    )
    assert closed == ([123] if opened else [])


@pytest.mark.parametrize("operation", ["is_dir", "is_file"])
def test_unreadable_phase_hints_do_not_interrupt_process_progress(
    tmp_path, monkeypatch, operation,
):
    counters = [0.0, None]
    watchdog, clock = _watchdog(tmp_path, probe=lambda _pid: tuple(counters))

    def denied(_path):
        raise PermissionError("phase hints unreadable")

    monkeypatch.setattr(Path, operation, denied)
    assert watchdog.sample() is None
    clock[0] = counters[0] = 61
    assert watchdog.sample() is None
    assert "sources=cpu" in watchdog.describe()
    clock[0] = counters[0] = 900
    assert watchdog.sample() == "absolute cap reached"
