"""Focused tests for the manifest-driven isolated FreeCAD launch scripts."""

from __future__ import annotations

import hashlib
import io
import importlib.util
import json
import os
import sys
import threading
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
MCP_ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(
        "isolated_test_" + name.replace(".py", ""), path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_setup_profile_creates_persistent_identity_secret_and_manifest(
    tmp_path, monkeypatch
):
    setup = _load_script("setup_isolated_profile.py")
    monkeypatch.setattr(setup, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(setup, "_freecad_mcp_root", lambda: MCP_ROOT)
    monkeypatch.setattr(
        setup,
        "_junction",
        lambda _source, destination: destination.mkdir(parents=True, exist_ok=True),
    )
    # ACL application has its own platform implementation; keep this test
    # independent from the host account/localized icacls output.
    monkeypatch.setattr(setup, "_restrict_owner_only", lambda _path: None)
    monkeypatch.setattr(sys, "argv", ["setup_isolated_profile.py", "--port", "19876"])

    assert setup.main() == 0
    profile = tmp_path / setup.PROFILE_NAME
    manifest_path = profile / setup.MANIFEST_FILENAME
    settings_path = profile / setup.SETTINGS_FILENAME
    secret_path = profile / setup.SECRET_FILENAME
    first_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first_secret = secret_path.read_bytes()

    assert len(first_secret) == 32
    assert first_manifest["schema_version"] == 1
    assert first_manifest["rpc_host"] == "127.0.0.1"
    assert first_manifest["rpc_port"] == 19876
    assert first_manifest["auth_secret_file"] == str(secret_path.resolve())
    assert all(
        first_manifest[key] is None
        for key in (
            "expected_freecad_pid",
            "expected_freecad_process_started_at",
            "expected_addon_runtime_id",
            "expected_boot_id",
            "expected_protocol_version",
            "expected_protocol_features",
            "expected_addon_version",
            "expected_addon_build_id",
            "expected_freecad_version",
            "expected_freecad_revision",
            "expected_profile_path_fingerprint",
        )
    )
    uuid.UUID(first_manifest["profile_instance_id"])
    manifest_text = manifest_path.read_text(encoding="utf-8")
    settings_text = settings_path.read_text(encoding="utf-8")
    assert first_secret.hex() not in manifest_text
    assert first_secret.hex() not in settings_text

    settings = json.loads(settings_text)
    assert settings["profile_instance_id"] == first_manifest["profile_instance_id"]
    assert settings["document_lease_mode"] == "enforce"
    assert settings["persist_task_summary_in_sidecar"] is False
    assert settings["rpc_bind_host"] == "127.0.0.1"
    assert settings["auth_secret_file"] == str(secret_path.resolve())

    # Rerunning setup retains both identity and secret.
    assert setup.main() == 0
    second_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert second_manifest["profile_instance_id"] == first_manifest["profile_instance_id"]
    assert second_manifest["created_at"] == first_manifest["created_at"]
    assert secret_path.read_bytes() == first_secret


def test_setup_profile_name_override_does_not_use_default_profile(
    tmp_path, monkeypatch
):
    setup = _load_script("setup_isolated_profile.py")
    monkeypatch.setattr(setup, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(setup, "_freecad_mcp_root", lambda: MCP_ROOT)
    monkeypatch.setattr(
        setup,
        "_junction",
        lambda _source, destination: destination.mkdir(parents=True, exist_ok=True),
    )
    monkeypatch.setattr(setup, "_restrict_owner_only", lambda _path: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_isolated_profile.py",
            "--port",
            "19877",
            "--profile-name",
            ".freecad-mcp-e2e-session",
        ],
    )

    assert setup.main() == 0
    assert (tmp_path / ".freecad-mcp-e2e-session" / setup.MANIFEST_FILENAME).is_file()
    assert not (tmp_path / setup.PROFILE_NAME).exists()
    manifest = json.loads(
        (tmp_path / ".freecad-mcp-e2e-session" / setup.MANIFEST_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    assert manifest["rpc_port"] == 19877


def test_setup_profile_dir_env_override(tmp_path, monkeypatch):
    setup = _load_script("setup_isolated_profile.py")
    custom = tmp_path / "custom-profile-dir"
    monkeypatch.setenv("FREECAD_MCP_PROFILE_DIR", str(custom))
    monkeypatch.setattr(setup, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(setup, "_freecad_mcp_root", lambda: MCP_ROOT)
    monkeypatch.setattr(
        setup,
        "_junction",
        lambda _source, destination: destination.mkdir(parents=True, exist_ok=True),
    )
    monkeypatch.setattr(setup, "_restrict_owner_only", lambda _path: None)
    monkeypatch.setattr(sys, "argv", ["setup_isolated_profile.py", "--port", "19878"])

    assert setup.main() == 0
    assert (custom / setup.MANIFEST_FILENAME).is_file()
    assert not (tmp_path / setup.PROFILE_NAME).exists()


def test_launcher_consume_profile_name_leaves_freecad_args() -> None:
    launcher = _load_script("start_freecad_isolated.py")
    name, rest = launcher._consume_launcher_args(
        ["--profile-name", ".freecad-mcp-e2e-session", "--", "Macro.FCMacro"]
    )
    assert name == ".freecad-mcp-e2e-session"
    assert rest == ["--", "Macro.FCMacro"]
    resolved = launcher._resolve_profile(Path("/repo"), profile_name=name)
    assert resolved == Path("/repo") / ".freecad-mcp-e2e-session"


def test_launcher_consumes_supervision_flag_without_forwarding_it() -> None:
    launcher = _load_script("start_freecad_isolated.py")

    supervise, rest = launcher._consume_supervision_flag(
        ["--", "Macro.FCMacro", "--supervise"]
    )

    assert supervise is True
    assert rest == ["--", "Macro.FCMacro"]


def test_supervised_posix_spawn_owns_new_session_and_disconnects_child_stdin(
    monkeypatch,
) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    process = SimpleNamespace(pid=4321)
    calls = []
    monkeypatch.setattr(launcher.sys, "platform", "linux")
    monkeypatch.setattr(launcher.os, "name", "posix")
    monkeypatch.setattr(
        launcher.subprocess,
        "Popen",
        lambda command, **kwargs: calls.append((command, kwargs)) or process,
    )

    spawned, owner = launcher._spawn_freecad_process(
        ["/branch/FreeCAD"],
        env={"TEST": "1"},
        cwd="/branch",
        supervise=True,
    )

    assert spawned is process
    assert owner.process is process
    assert calls == [
        (
            ["/branch/FreeCAD"],
            {
                "env": {"TEST": "1"},
                "cwd": "/branch",
                "stdin": launcher.subprocess.DEVNULL,
                "creationflags": 0,
                "close_fds": True,
                "start_new_session": True,
            },
        )
    ]


def test_posix_supervisor_never_polls_or_signals_reusable_pid_before_group_kill(
    monkeypatch,
) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    events = []

    class Process:
        pid = 4321

        @staticmethod
        def poll():
            pytest.fail("supervised POSIX child must not be polled/reaped")

        @staticmethod
        def send_signal(_signal):
            pytest.fail("supervised POSIX child must be signalled by exact group")

        @staticmethod
        def wait(*, timeout):
            events.append(("wait", timeout))
            return -9

    monkeypatch.setattr(
        launcher.os,
        "killpg",
        lambda group, sig: events.append(("killpg", group, sig)),
        raising=False,
    )
    monkeypatch.setattr(
        launcher.time,
        "sleep",
        lambda seconds: events.append(("sleep", seconds)),
    )
    monkeypatch.setattr(launcher.signal, "SIGKILL", 9, raising=False)
    owner = launcher._SupervisedChild(Process())

    owner.terminate_exact_tree(grace_seconds=0.25)

    assert events == [
        ("killpg", 4321, launcher.signal.SIGTERM),
        ("sleep", 0.25),
        ("killpg", 4321, 9),
        ("wait", 1.0),
    ]


def test_windows_job_assignment_precedes_resume() -> None:
    launcher = _load_script("start_freecad_isolated.py")
    events = []

    class Kernel:
        @staticmethod
        def AssignProcessToJobObject(job, process):
            events.append(("assign", job, process))
            return True

        @staticmethod
        def ResumeThread(thread):
            events.append(("resume", thread))
            return 1

    job = launcher._WindowsLifetimeJob.__new__(launcher._WindowsLifetimeJob)
    job._handle = "job-handle"
    job._kernel32 = Kernel()
    job._ctypes = SimpleNamespace(get_last_error=lambda: 0)

    job.bind_suspended_process("process-handle", "thread-handle")

    assert events == [
        ("assign", "job-handle", "process-handle"),
        ("resume", "thread-handle"),
    ]


def test_supervisor_sigterm_requests_owned_cleanup_outside_signal_handler(
    monkeypatch,
) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    events = []
    handlers = {}

    def install(sig, handler):
        previous = handlers.get(sig, "previous")
        handlers[sig] = handler
        return previous

    read_started = threading.Event()
    release_reader = threading.Event()

    class BlockingControlPipe:
        @staticmethod
        def readline():
            read_started.set()
            release_reader.wait(1.0)
            return ""

    owner = SimpleNamespace(
        terminate_exact_tree=lambda: events.append("terminate-owned-tree")
    )
    monkeypatch.setattr(launcher.signal, "signal", install)
    control = launcher._SupervisorControl(BlockingControlPipe())
    control.start()
    assert read_started.wait(0.5)
    handlers[launcher.signal.SIGTERM](launcher.signal.SIGTERM, None)

    assert launcher._supervise_until_stop(owner, control) == 0
    assert events == ["terminate-owned-tree"]
    release_reader.set()
    control.close()


def test_supervisor_consumes_stop_before_readiness_wait_begins(monkeypatch) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    monkeypatch.setattr(launcher.signal, "signal", lambda _sig, _handler: None)
    control = launcher._SupervisorControl(io.StringIO("STOP\n"))

    control.start()

    assert control.wait(0.5) is True
    assert control.requested() is True
    assert control.exit_code() == 0
    control.close()


def test_control_start_failure_closes_newly_spawned_owner(monkeypatch) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    events = []
    monkeypatch.setattr(
        launcher,
        "_spawn_freecad_process",
        lambda *_args, **_kwargs: pytest.fail(
            "control handlers must be installed before child spawn"
        ),
    )

    class FailingControl:
        @staticmethod
        def start():
            raise RuntimeError("control monitor failed")

    monkeypatch.setattr(launcher, "_SupervisorControl", FailingControl)

    with pytest.raises(RuntimeError, match="control monitor failed"):
        launcher._spawn_supervised_process_with_control(
            ["/branch/FreeCAD"], env={}, cwd="/branch"
        )

    assert events == []


def test_preinstalled_control_stop_prevents_child_spawn(monkeypatch) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    events = []

    class RequestedControl:
        def start(self):
            events.append("start-control")

        @staticmethod
        def requested():
            return True

        def close(self):
            events.append("close-control")

    monkeypatch.setattr(launcher, "_SupervisorControl", RequestedControl)
    monkeypatch.setattr(
        launcher,
        "_spawn_freecad_process",
        lambda *_args, **_kwargs: pytest.fail(
            "requested control must prevent child spawn"
        ),
    )

    with pytest.raises(InterruptedError, match="before child spawn"):
        launcher._spawn_supervised_process_with_control(
            ["/branch/FreeCAD"], env={}, cwd="/branch"
        )

    assert events == ["start-control", "close-control"]


def test_stop_arriving_during_spawn_terminates_owner_before_raising(monkeypatch) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    events = []

    class Control:
        checks = 0

        def start(self):
            events.append("start-control")

        def requested(self):
            self.checks += 1
            return self.checks > 1

        def close(self):
            events.append("close-control")

    class Owner:
        _terminated = False

        def terminate_exact_tree(self):
            events.append("terminate-owner")

        def close(self):
            events.append("close-owner")

    monkeypatch.setattr(launcher, "_SupervisorControl", Control)
    monkeypatch.setattr(
        launcher,
        "_spawn_freecad_process",
        lambda *_args, **_kwargs: (SimpleNamespace(pid=4321), Owner()),
    )

    with pytest.raises(InterruptedError, match="during child spawn"):
        launcher._spawn_supervised_process_with_control(
            ["/branch/FreeCAD"], env={}, cwd="/branch"
        )

    assert events == [
        "start-control",
        "terminate-owner",
        "close-owner",
        "close-control",
    ]


def test_control_handlers_restore_only_after_owner_teardown(monkeypatch) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    events = []

    class Owner:
        def close(self):
            events.append("close-owner")

    class Control:
        def close(self):
            events.append("restore-handlers")

    launcher._close_supervised_lifecycle(Owner(), Control())

    assert events == ["close-owner", "restore-handlers"]


def test_early_stop_reports_nonzero_when_exact_tree_shutdown_fails(monkeypatch) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    monkeypatch.setattr(launcher.signal, "signal", lambda _sig, _handler: None)
    control = launcher._SupervisorControl(io.StringIO("STOP\n"))
    control.start()
    assert control.wait(0.5)

    class FailingOwner:
        @staticmethod
        def terminate_exact_tree():
            raise OSError("job/group termination failed")

    assert launcher._supervise_until_stop(FailingOwner(), control) == 1
    control.close()


def test_windows_create_process_is_suspended_bound_then_thread_handle_closed() -> None:
    launcher = _load_script("start_freecad_isolated.py")
    import ctypes
    from ctypes import wintypes

    events = []

    class Call:
        def __init__(self, implementation):
            self.implementation = implementation

        def __call__(self, *args):
            return self.implementation(*args)

    null_handles = iter((101, 102))

    def create_file(*_args):
        handle = next(null_handles)
        events.append(("create-null", handle))
        return handle

    def create_process(
        application,
        _command,
        _process_security,
        _thread_security,
        inherit_handles,
        flags,
        _environment,
        cwd,
        startup_pointer,
        info_pointer,
    ):
        startup = startup_pointer._obj.StartupInfo
        info = info_pointer._obj
        events.append(
            (
                "create-suspended",
                application,
                bool(inherit_handles),
                int(flags),
                cwd,
                int(startup.hStdInput),
                int(startup.hStdOutput),
            )
        )
        info.hProcess = 201
        info.hThread = 202
        info.dwProcessId = 4321
        info.dwThreadId = 1
        return True

    class Kernel:
        CreateFileW = Call(create_file)
        CreateProcessW = Call(create_process)

        @staticmethod
        def InitializeProcThreadAttributeList(
            attribute_list, _count, _flags, size_pointer
        ):
            if attribute_list is None:
                size_pointer._obj.value = 128
                events.append("size-attribute-list")
                return False
            events.append("initialize-attribute-list")
            return True

        @staticmethod
        def UpdateProcThreadAttribute(
            _attribute_list,
            _flags,
            attribute,
            _value,
            value_size,
            _previous,
            _return_size,
        ):
            events.append(("restrict-handles", int(attribute), int(value_size)))
            return True

        @staticmethod
        def DeleteProcThreadAttributeList(_attribute_list):
            events.append("delete-attribute-list")

        @staticmethod
        def CloseHandle(handle):
            events.append(("close", int(handle)))
            return True

    class Job:
        _ctypes = ctypes
        _wintypes = wintypes
        _kernel32 = Kernel()

        @staticmethod
        def bind_suspended_process(process_handle, thread_handle):
            events.append(("bind-and-resume", int(process_handle), int(thread_handle)))

    process = launcher._create_windows_suspended_process(
        ["C:/branch/FreeCAD.exe", "--console"],
        env={"A": "1"},
        cwd="C:/branch",
        job=Job(),
    )

    assert process.pid == 4321
    assert events[:4] == [
        ("create-null", 101),
        ("create-null", 102),
        "size-attribute-list",
        "initialize-attribute-list",
    ]
    restrict_event = events[4]
    assert restrict_event[0:2] == ("restrict-handles", 0x00020002)
    assert restrict_event[2] == 2 * ctypes.sizeof(wintypes.HANDLE)
    create_event = events[5]
    assert create_event[:3] == (
        "create-suspended",
        "C:/branch/FreeCAD.exe",
        True,
    )
    flags = create_event[3]
    assert flags & 0x00000004  # CREATE_SUSPENDED
    assert flags & 0x00080000  # EXTENDED_STARTUPINFO_PRESENT
    assert events[6:] == [
        "delete-attribute-list",
        ("close", 101),
        ("close", 102),
        ("bind-and-resume", 201, 202),
        ("close", 202),
    ]
    process.close()
    assert events[-1] == ("close", 201)


def test_launcher_profile_dir_env_override(tmp_path, monkeypatch) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    custom = tmp_path / "launcher-profile"
    monkeypatch.setenv("FREECAD_MCP_PROFILE_DIR", str(custom))
    assert launcher._resolve_profile(Path("/repo")) == custom


def test_launcher_freecad_executable_override_wins(tmp_path, monkeypatch) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    branch_freecad = tmp_path / "build" / "debug" / "bin" / "BranchFreeCAD"
    branch_freecad.parent.mkdir(parents=True)
    branch_freecad.touch()
    branch_freecad.chmod(0o755)
    monkeypatch.setenv(launcher.FREECAD_EXECUTABLE_ENV, str(branch_freecad.resolve()))

    assert launcher._resolve_freecad_executable(tmp_path) == branch_freecad.resolve()


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable bits only")
def test_launcher_rejects_non_executable_override(tmp_path, monkeypatch) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    branch_freecad = tmp_path / "build" / "debug" / "bin" / "BranchFreeCAD"
    branch_freecad.parent.mkdir(parents=True)
    branch_freecad.touch(mode=0o600)
    monkeypatch.setenv(launcher.FREECAD_EXECUTABLE_ENV, str(branch_freecad.resolve()))

    with pytest.raises(SystemExit, match="is not executable"):
        launcher._resolve_freecad_executable(tmp_path)


@pytest.mark.parametrize("configured", ["relative/FreeCAD", "missing/FreeCAD.exe"])
def test_launcher_rejects_invalid_freecad_override_before_endpoint_or_spawn(
    tmp_path, monkeypatch, configured
) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    if configured.startswith("missing/"):
        configured = str((tmp_path / configured).resolve())
    monkeypatch.setenv(launcher.FREECAD_EXECUTABLE_ENV, configured)
    monkeypatch.setattr(launcher, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        launcher,
        "_reserve_endpoint",
        lambda *_args: pytest.fail("invalid executable must fail before reservation"),
    )
    monkeypatch.setattr(
        launcher.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("invalid executable must not spawn"),
    )
    monkeypatch.setattr(sys, "argv", ["start_freecad_isolated.py"])

    with pytest.raises(SystemExit, match="FREECAD_MCP_ISOLATED_FREECAD"):
        launcher.main()


@pytest.mark.parametrize(
    ("platform", "executable_name"),
    [("win32", "FreeCAD.exe"), ("linux", "FreeCAD")],
)
def test_launcher_default_executable_is_platform_specific(
    tmp_path, monkeypatch, platform, executable_name
) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    expected = tmp_path / "build" / "release" / "bin" / executable_name
    expected.parent.mkdir(parents=True)
    expected.touch()
    expected.chmod(0o755)
    monkeypatch.delenv(launcher.FREECAD_EXECUTABLE_ENV, raising=False)
    monkeypatch.setattr(launcher.sys, "platform", platform)

    assert launcher._resolve_freecad_executable(tmp_path) == expected


def test_setup_refuses_to_replace_persistent_profile_identity(tmp_path):
    setup = _load_script("setup_isolated_profile.py")
    profile = tmp_path / setup.PROFILE_NAME
    profile.mkdir()
    existing_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())
    manifest = setup._build_manifest(
        profile=profile,
        profile_id=existing_id,
        secret_path=profile / setup.SECRET_FILENAME,
        rpc_port=9876,
        existing=None,
    )
    setup._atomic_write_json(profile / setup.MANIFEST_FILENAME, manifest)
    with pytest.raises(SystemExit, match="Refusing to replace"):
        setup._persistent_profile_id(profile, other_id)


def test_windows_secret_permissions_remove_inheritance(tmp_path, monkeypatch):
    setup = _load_script("setup_isolated_profile.py")
    secret = tmp_path / "auth.secret"
    secret.write_bytes(b"s" * 32)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command == ["whoami"]:
            return SimpleNamespace(stdout="example\\owner\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(setup.sys, "platform", "win32")
    monkeypatch.setattr(setup.subprocess, "run", fake_run)
    setup._restrict_owner_only(secret)
    assert calls[1][0] == [
        "icacls",
        str(secret),
        "/inheritance:r",
        "/grant:r",
        "example\\owner:(F)",
    ]
    assert calls[1][1]["check"] is True


def _runtime_info(profile: Path, *, pid: int = 4321) -> dict:
    return {
        "ok": True,
        "instance_id": "profile-a",
        "profile_instance_id": "profile-a",
        "addon_runtime_id": str(uuid.uuid4()),
        "pid": pid,
        "freecad_process_started_at": "2026-07-22T10:00:00Z",
        "boot_id": "test-boot-id",
        "host": "127.0.0.1",
        "port": 19876,
        "actual_endpoint": {"host": "127.0.0.1", "port": 19876},
        "profile_path": str(profile),
        "protocol_versions": [1, 2],
        "protocol_version": 2,
        "protocol_features": [
            "authenticated_sessions",
            "document_session_identity",
            "lease_credentials_v2",
            "request_idempotency",
            "runtime_binding",
        ],
        "addon_version": "0.1.20",
        "addon_build_id": "freecad-mcp-addon-test",
        "freecad_version": [1, 1, 0, "revision-test"],
        "profile_path_fingerprint": hashlib.sha256(
            os.path.normcase(os.path.realpath(profile)).encode("utf-8")
        ).hexdigest(),
        "document_lease_mode": "enforce",
    }


def _launch_manifest(profile: Path) -> dict:
    return {
        "schema_version": 1,
        "rpc_host": "127.0.0.1",
        "rpc_port": 19876,
        "profile_instance_id": "profile-a",
        "profile_path": str(profile),
        "auth_secret_file": str(profile / "auth.secret"),
        "expected_freecad_pid": 4321,
        "expected_freecad_process_started_at": None,
        "expected_addon_runtime_id": None,
        "expected_boot_id": None,
        "expected_protocol_version": None,
        "expected_protocol_features": None,
        "expected_addon_version": None,
        "expected_addon_build_id": None,
        "expected_freecad_version": None,
        "expected_freecad_revision": None,
        "expected_profile_path_fingerprint": None,
        "created_at": "2026-07-22T09:00:00Z",
    }


def test_launcher_validates_and_records_exact_runtime_identity(tmp_path):
    launcher = _load_script("start_freecad_isolated.py")
    manifest = _launch_manifest(tmp_path)
    info = _runtime_info(tmp_path)
    expectations = launcher._validate_instance_info(info, manifest, 4321)
    assert expectations == {
        "expected_freecad_pid": 4321,
        "expected_freecad_process_started_at": "2026-07-22T10:00:00Z",
        "expected_addon_runtime_id": info["addon_runtime_id"],
        "expected_boot_id": "test-boot-id",
        "expected_protocol_version": 2,
        "expected_protocol_features": sorted(info["protocol_features"]),
        "expected_addon_version": "0.1.20",
        "expected_addon_build_id": "freecad-mcp-addon-test",
        "expected_freecad_version": "1.1.0",
        "expected_freecad_revision": "revision-test",
        "expected_profile_path_fingerprint": info[
            "profile_path_fingerprint"
        ],
    }


def _authenticated_proxy(launcher, profile: Path, info: dict, secret: bytes):
    """Return an in-process addon protocol endpoint for launcher tests."""

    from addon.FreeCADMCP.rpc_server.lease_protocol import (
        SessionManager,
        make_runtime_manifest,
    )

    runtime_manifest = make_runtime_manifest(
        profile_id=info["profile_instance_id"],
        addon_runtime_id=info["addon_runtime_id"],
        freecad_pid=info["pid"],
        freecad_process_started_at=info["freecad_process_started_at"],
        boot_id="test-boot-id",
        rpc_host=info["actual_endpoint"]["host"],
        rpc_port=info["actual_endpoint"]["port"],
        freecad_version=launcher._freecad_build_identity(info["freecad_version"])[0],
        freecad_revision=launcher._freecad_build_identity(info["freecad_version"])[1],
        addon_version="0.1.20",
        addon_build_id=info["addon_build_id"],
        profile_path_fingerprint=launcher._profile_path_fingerprint(profile),
    )
    manager = SessionManager(manifest=runtime_manifest, secret=secret)

    class Proxy:
        requests: ClassVar[list] = []

        def handshake_v2(self, payload):
            self.requests.append(payload)
            return manager.perform_handshake(payload)

    return Proxy()


def test_launcher_persists_only_hmac_authenticated_runtime_facts(tmp_path):
    launcher = _load_script("start_freecad_isolated.py")
    manifest = _launch_manifest(tmp_path)
    info = _runtime_info(tmp_path)
    secret = b"s" * 32
    proxy = _authenticated_proxy(launcher, tmp_path, info, secret)

    expectations = launcher._prove_authenticated_instance(
        proxy,
        info=info,
        manifest=manifest,
        launched_pid=4321,
        secret=secret,
    )

    assert expectations == {
        "expected_freecad_pid": 4321,
        "expected_freecad_process_started_at": "2026-07-22T10:00:00.000000Z",
        "expected_addon_runtime_id": info["addon_runtime_id"],
        "expected_boot_id": "test-boot-id",
        "expected_protocol_version": 2,
        "expected_protocol_features": sorted(info["protocol_features"]),
        "expected_addon_version": "0.1.20",
        "expected_addon_build_id": "freecad-mcp-addon-test",
        "expected_freecad_version": "1.1.0",
        "expected_freecad_revision": "revision-test",
        "expected_profile_path_fingerprint": info[
            "profile_path_fingerprint"
        ],
    }
    request = proxy.requests[0]
    assert request["expected_server"] == {
        "profile_id": "profile-a",
        "freecad_pid": 4321,
        "freecad_process_started_at": "2026-07-22T10:00:00.000000Z",
        "addon_runtime_id": info["addon_runtime_id"],
        "boot_id": "test-boot-id",
        "rpc_host": "127.0.0.1",
        "rpc_port": 19876,
        "protocol_version": 2,
        "features": sorted(info["protocol_features"]),
        "addon_version": "0.1.20",
        "addon_build_id": "freecad-mcp-addon-test",
        "freecad_version": "1.1.0",
        "freecad_revision": "revision-test",
        "profile_path_fingerprint": info["profile_path_fingerprint"],
    }
    assert request["proof"].startswith("hmac-sha256:")
    assert secret.hex() not in json.dumps(request)


def test_launcher_rejects_unsigned_handshake_response(tmp_path):
    launcher = _load_script("start_freecad_isolated.py")
    manifest = _launch_manifest(tmp_path)
    info = _runtime_info(tmp_path)

    class UnauthenticatedProxy:
        def handshake_v2(self, request):
            # An endpoint can copy every discovery assertion, but cannot make
            # it readiness evidence without the profile-secret HMAC.
            return {
                "ok": True,
                "client_nonce": request["client_nonce"],
                "manifest": dict(info),
            }

    with pytest.raises(
        launcher.InstanceValidationError,
        match="authenticated RPC v2 handshake failed",
    ):
        launcher._prove_authenticated_instance(
            UnauthenticatedProxy(),
            info=info,
            manifest=manifest,
            launched_pid=4321,
            secret=b"s" * 32,
        )


def test_launcher_rejects_authenticated_wrong_profile_path(tmp_path):
    launcher = _load_script("start_freecad_isolated.py")
    manifest = _launch_manifest(tmp_path)
    info = _runtime_info(tmp_path)
    secret = b"s" * 32
    proxy = _authenticated_proxy(launcher, tmp_path / "other-profile", info, secret)

    with pytest.raises(
        launcher.InstanceValidationError,
        match="authenticated RPC v2 handshake failed",
    ):
        launcher._prove_authenticated_instance(
            proxy,
            info=info,
            manifest=manifest,
            launched_pid=4321,
            secret=secret,
        )


def test_launcher_does_not_write_readiness_before_handshake_verifies(
    tmp_path, monkeypatch
):
    launcher = _load_script("start_freecad_isolated.py")
    profile = tmp_path / launcher.PROFILE_NAME
    profile.mkdir()
    freecad = tmp_path / "build" / "debug" / "bin" / "BranchFreeCAD.exe"
    freecad.parent.mkdir(parents=True)
    freecad.touch()
    freecad.chmod(0o755)
    secret = profile / "auth.secret"
    secret.write_bytes(b"s" * 32)
    secret.chmod(0o600)
    manifest = _launch_manifest(profile)
    manifest["auth_secret_file"] = str(secret)
    (profile / launcher.MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    class Process:
        pid = 4321
        returncode = None
        terminated = False

        def poll(self):
            return 0 if self.terminated else None

        def terminate(self):
            self.terminated = True
            self.returncode = 0

        def wait(self, *, timeout):
            del timeout
            if not self.terminated:
                raise launcher.subprocess.TimeoutExpired("FreeCAD", 1)
            return self.returncode

        def kill(self):
            self.terminated = True
            self.returncode = -9

    class Proxy:
        @staticmethod
        def get_instance_info():
            return _runtime_info(profile)

        @staticmethod
        def handshake_v2(request):
            return {"client_nonce": request["client_nonce"], "proof": "not-a-proof"}

    writes = []
    monkeypatch.setattr(launcher, "_repo_root", lambda: tmp_path)
    monkeypatch.setenv(launcher.FREECAD_EXECUTABLE_ENV, str(freecad.resolve()))
    reservation = SimpleNamespace(closed=False)

    def close_reservation():
        reservation.closed = True

    reservation.close = close_reservation
    monkeypatch.setattr(launcher, "_reserve_endpoint", lambda *_args: reservation)
    monkeypatch.setattr(
        launcher,
        "_load_parent_start_freecad",
        lambda: SimpleNamespace(_launch_env=lambda _executable: {}),
    )

    spawned = []

    def spawn(command, **kwargs):
        assert reservation.closed is True
        assert command == [str(freecad.resolve())]
        assert kwargs["start_new_session"] is (os.name != "nt")
        assert kwargs["stdin"] is None
        process = Process()
        spawned.append(process)
        return process

    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    class Connection:
        def __init__(self, *args, **kwargs):
            self.server = Proxy()

        @staticmethod
        def disconnect():
            return None

    monkeypatch.setattr(launcher, "FreeCADConnection", Connection)
    monkeypatch.setattr(
        launcher, "_write_manifest", lambda profile_path, value: writes.append(value)
    )
    monkeypatch.setattr(sys, "argv", ["start_freecad_isolated.py"])

    assert launcher.main() == 1
    assert writes == []
    assert spawned[0].terminated is True
    assert not (profile / launcher.LAUNCH_STATE_FILENAME).exists()


def test_launcher_preserves_launch_state_when_exact_child_resists_cleanup(
    tmp_path, monkeypatch
) -> None:
    launcher = _load_script("start_freecad_isolated.py")
    profile = tmp_path / launcher.PROFILE_NAME
    profile.mkdir()
    freecad = tmp_path / "BranchFreeCAD"
    freecad.touch()
    freecad.chmod(0o755)
    secret = profile / "auth.secret"
    secret.write_bytes(b"s" * 32)
    secret.chmod(0o600)
    manifest = _launch_manifest(profile)
    manifest["auth_secret_file"] = str(secret)
    (profile / launcher.MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    class Process:
        pid = 8765
        returncode = None

        @staticmethod
        def poll():
            return None

    monkeypatch.setattr(launcher, "_repo_root", lambda: tmp_path)
    monkeypatch.setenv(launcher.FREECAD_EXECUTABLE_ENV, str(freecad.resolve()))
    reservation = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(launcher, "_reserve_endpoint", lambda *_args: reservation)
    monkeypatch.setattr(
        launcher,
        "_load_parent_start_freecad",
        lambda: SimpleNamespace(_launch_env=lambda _executable: {}),
    )
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(
        launcher,
        "_terminate_spawned_process",
        lambda _process: False,
    )

    class Connection:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("post-spawn setup failed")

    monkeypatch.setattr(launcher, "FreeCADConnection", Connection)
    monkeypatch.setattr(sys, "argv", ["start_freecad_isolated.py"])

    with pytest.raises(RuntimeError, match="post-spawn setup failed"):
        launcher.main()

    state = json.loads(
        (profile / launcher.LAUNCH_STATE_FILENAME).read_text(encoding="utf-8")
    )
    assert state["freecad_pid"] == 8765
    assert Path(state["profile_path"]) == profile.resolve()


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("profile_instance_id", "other", "profile mismatch"),
        ("pid", 9999, "PID mismatch"),
        ("profile_path", "C:/not-the-profile", "profile path mismatch"),
        ("document_lease_mode", "observe", "not in document_lease_mode=enforce"),
    ],
)
def test_launcher_rejects_mismatched_runtime(tmp_path, field, value, match):
    launcher = _load_script("start_freecad_isolated.py")
    info = _runtime_info(tmp_path)
    info[field] = value
    with pytest.raises(launcher.InstanceValidationError, match=match):
        launcher._validate_instance_info(info, _launch_manifest(tmp_path), 4321)


def test_launcher_refuses_occupied_endpoint_without_rpc_probe(monkeypatch):
    launcher = _load_script("start_freecad_isolated.py")
    existing = launcher.socket.socket(launcher.socket.AF_INET, launcher.socket.SOCK_STREAM)
    existing.bind(("127.0.0.1", 0))
    existing.listen(1)
    port = existing.getsockname()[1]
    monkeypatch.setattr(
        launcher.socket,
        "create_connection",
        lambda *_args, **_kwargs: pytest.fail("occupied-port check must not connect"),
    )
    try:
        with pytest.raises(SystemExit, match="already occupied"):
            launcher._reserve_endpoint("127.0.0.1", port)
    finally:
        existing.close()


def test_launcher_reservation_closes_pre_spawn_bind_window():
    launcher = _load_script("start_freecad_isolated.py")
    probe = launcher.socket.socket(launcher.socket.AF_INET, launcher.socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    reservation = launcher._reserve_endpoint("127.0.0.1", port)
    competing = launcher.socket.socket(
        launcher.socket.AF_INET, launcher.socket.SOCK_STREAM
    )
    try:
        with pytest.raises(OSError):
            competing.bind(("127.0.0.1", port))
        reservation.close()
        competing.bind(("127.0.0.1", port))
    finally:
        reservation.close()
        competing.close()


def test_launcher_never_spawns_or_reuses_when_manifest_endpoint_is_occupied(
    tmp_path, monkeypatch
):
    launcher = _load_script("start_freecad_isolated.py")
    profile = tmp_path / launcher.PROFILE_NAME
    profile.mkdir()
    executable_name = "FreeCAD.exe" if launcher.sys.platform == "win32" else "FreeCAD"
    freecad = tmp_path / "build" / "release" / "bin" / executable_name
    freecad.parent.mkdir(parents=True)
    freecad.touch()
    freecad.chmod(0o755)
    secret = profile / "auth.secret"
    secret.write_bytes(b"s" * 32)
    secret.chmod(0o600)
    manifest = _launch_manifest(profile)
    manifest["auth_secret_file"] = str(secret)
    (profile / launcher.MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    spawned = []

    def occupied(*_args):
        raise SystemExit("already occupied")

    monkeypatch.setattr(launcher, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(launcher, "_reserve_endpoint", occupied)
    monkeypatch.setattr(
        launcher.subprocess,
        "Popen",
        lambda *args, **kwargs: spawned.append((args, kwargs)),
    )

    with pytest.raises(SystemExit, match="already occupied"):
        launcher.main()
    assert spawned == []


@pytest.mark.parametrize(
    "script_name", ["start_freecad_isolated.py", "setup_cursor_mcp_isolated.py"]
)
def test_isolated_manifest_rejects_non_loopback_endpoint(
    tmp_path, script_name
):
    script = _load_script(script_name)
    profile = tmp_path / "profile"
    profile.mkdir()
    secret = profile / "auth.secret"
    secret.write_bytes(b"s" * 32)
    secret.chmod(0o600)
    manifest = _launch_manifest(profile)
    manifest["rpc_host"] = "192.0.2.20"
    manifest["auth_secret_file"] = str(secret)
    path = profile / "instance-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SystemExit, match="loopback"):
        if script_name == "start_freecad_isolated.py":
            script._load_manifest(profile)
        else:
            script.load_instance_manifest(path)


@pytest.mark.parametrize(
    "script_name", ["start_freecad_isolated.py", "setup_cursor_mcp_isolated.py"]
)
def test_isolated_manifest_rejects_unknown_fields(tmp_path, script_name):
    script = _load_script(script_name)
    profile = tmp_path / "profile"
    profile.mkdir()
    secret = profile / "auth.secret"
    secret.write_bytes(b"s" * 32)
    secret.chmod(0o600)
    manifest = _launch_manifest(profile)
    manifest["auth_secret_file"] = str(secret)
    manifest["unexpected_downgrade_flag"] = True
    path = profile / "instance-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SystemExit, match=r"extra=.*unexpected_downgrade_flag"):
        if script_name == "start_freecad_isolated.py":
            script._load_manifest(profile)
        else:
            script.load_instance_manifest(path)


def test_cursor_manifest_rejects_missing_or_non_32_byte_secret(tmp_path):
    cursor = _load_script("setup_cursor_mcp_isolated.py")
    secret = tmp_path / "secret"
    secret.write_bytes(b"short")
    manifest = _launch_manifest(tmp_path)
    manifest["auth_secret_file"] = str(secret)
    path = tmp_path / "instance-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SystemExit, match="32-byte"):
        cursor.load_instance_manifest(path)


def test_run_wrapper_forwards_manifest_auth_and_canonical_endpoint(
    tmp_path, monkeypatch
):
    runner = _load_script("run_freecad_mcp.py")
    captured = {}
    manifest = tmp_path / "instance-manifest.json"
    secret = tmp_path / "auth.secret"

    def fake_run(extra):
        captured["extra"] = extra
        return 0

    monkeypatch.setattr(runner, "_run_inprocess", fake_run)
    monkeypatch.delenv("FREECAD_MCP_DEBUG", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_freecad_mcp.py",
            "--host",
            "127.0.0.1",
            "--port",
            "19876",
            "--instance-id",
            "profile-a",
            "--instance-manifest",
            str(manifest),
            "--auth-file",
            str(secret),
        ],
    )
    assert runner.main() == 0
    assert captured["extra"] == [
        "--rpc-host",
        "127.0.0.1",
        "--rpc-port",
        "19876",
        "--instance-id",
        "profile-a",
        "--instance-manifest",
        str(manifest),
        "--auth-file",
        str(secret),
    ]
    command = runner._instrumented_command(captured["extra"])
    assert command[1:3] == ["-c", "from freecad_mcp.server import main; main()"]
