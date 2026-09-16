"""Non-live safety tests for the opt-in session E2E supervisor lifecycle."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tests.e2e import test_gui_lane_stays_unblocked as session_e2e


def _profile(tmp_path, monkeypatch):
    monkeypatch.setattr(session_e2e, "REPO_ROOT", tmp_path)
    profile = tmp_path / session_e2e.PROFILE_NAME
    profile.mkdir()
    manifest_path = profile / "instance-manifest.json"
    manifest = {
        "rpc_host": "127.0.0.1",
        "rpc_port": session_e2e.E2E_PORT,
        "profile_path": str(profile.resolve()),
        "profile_instance_id": "profile-id",
        "expected_freecad_pid": 4242,
        "expected_freecad_process_started_at": "2026-01-01T00:00:00Z",
        "expected_addon_runtime_id": "runtime-id",
        "expected_boot_id": "boot-id",
        "expected_profile_path_fingerprint": "sha256:test",
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return profile, manifest_path, manifest


def _verified(profile, manifest, *, pid=4242):
    runtime = SimpleNamespace(
        freecad_pid=pid,
        addon_runtime_id=manifest["expected_addon_runtime_id"],
        profile_id=manifest["profile_instance_id"],
        freecad_process_started_at=manifest[
            "expected_freecad_process_started_at"
        ],
        boot_id=manifest["expected_boot_id"],
        rpc_host="127.0.0.1",
        rpc_port=session_e2e.E2E_PORT,
        profile_path_fingerprint=manifest[
            "expected_profile_path_fingerprint"
        ],
    )
    info = {
        "pid": pid,
        "addon_runtime_id": runtime.addon_runtime_id,
        "profile_instance_id": runtime.profile_id,
        "profile_path": str(profile.resolve()),
        "actual_endpoint": {
            "host": "127.0.0.1",
            "port": session_e2e.E2E_PORT,
        },
    }
    connection = SimpleNamespace(
        get_instance_info=lambda: info,
        disconnect=lambda: None,
    )
    return connection, SimpleNamespace(manifest=runtime), "client-runtime"


class _ControlPipe:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.flushes = 0
        self.closed = False

    def write(self, command: str) -> None:
        self.commands.append(command)

    def flush(self) -> None:
        self.flushes += 1


class _Supervisor:
    def __init__(self, *, returncode=None, wait_result=0, on_wait=None) -> None:
        self.returncode = returncode
        self.wait_result = wait_result
        self.on_wait = on_wait
        self.stdin = _ControlPipe()
        self.waits: list[float] = []

    def poll(self):
        return self.returncode

    def wait(self, *, timeout):
        self.waits.append(timeout)
        if self.on_wait is not None:
            self.on_wait()
        self.returncode = self.wait_result
        return self.wait_result


def test_authenticated_retained_supervisor_stops_exact_tree_and_removes_profile(
    tmp_path, monkeypatch
):
    profile, manifest_path, manifest = _profile(tmp_path, monkeypatch)
    endpoint = {"up": True}
    supervisor = _Supervisor(on_wait=lambda: endpoint.update(up=False))
    monkeypatch.setattr(
        session_e2e,
        "_endpoint_accepts",
        lambda *_args: endpoint["up"],
    )
    monkeypatch.setattr(
        session_e2e,
        "_handshake_connection",
        lambda *_args, **_kwargs: _verified(profile, manifest),
    )

    session_e2e._cleanup_throwaway_session(
        profile,
        manifest_path,
        supervisor=supervisor,
        launch_manifest=manifest,
    )

    assert supervisor.stdin.commands == ["STOP\n"]
    assert supervisor.stdin.flushes == 1
    assert supervisor.waits == [session_e2e.CHILD_STOP_TIMEOUT_SECONDS]
    assert not profile.exists()


def test_authenticated_pid_replacement_never_commands_supervisor_or_deletes(
    tmp_path, monkeypatch
):
    profile, manifest_path, manifest = _profile(tmp_path, monkeypatch)
    supervisor = _Supervisor()
    monkeypatch.setattr(
        session_e2e,
        "_handshake_connection",
        lambda *_args, **_kwargs: _verified(profile, manifest, pid=9999),
    )

    with pytest.raises(
        session_e2e.SessionCleanupSafetyError,
        match="exact retained supervisor was stopped",
    ):
        session_e2e._cleanup_throwaway_session(
            profile,
            manifest_path,
            supervisor=supervisor,
            launch_manifest=manifest,
        )

    assert supervisor.stdin.commands == ["STOP\n"]
    assert supervisor.waits == [session_e2e.CHILD_STOP_TIMEOUT_SECONDS]
    assert profile.is_dir()


def test_manifest_identity_replacement_never_authenticates_or_commands(
    tmp_path, monkeypatch
):
    profile, manifest_path, manifest = _profile(tmp_path, monkeypatch)
    supervisor = _Supervisor()
    replacement = dict(manifest, expected_freecad_pid=9999)
    manifest_path.write_text(json.dumps(replacement), encoding="utf-8")
    monkeypatch.setattr(
        session_e2e,
        "_handshake_connection",
        lambda *_args, **_kwargs: pytest.fail(
            "changed manifest must not be upgraded into cleanup authority"
        ),
    )

    with pytest.raises(
        session_e2e.SessionCleanupSafetyError,
        match="exact retained supervisor was stopped",
    ):
        session_e2e._cleanup_throwaway_session(
            profile,
            manifest_path,
            supervisor=supervisor,
            launch_manifest=manifest,
        )

    assert supervisor.stdin.commands == ["STOP\n"]
    assert supervisor.waits == [session_e2e.CHILD_STOP_TIMEOUT_SECONDS]
    assert profile.is_dir()


def test_handshake_failure_still_stops_exact_retained_supervisor(
    tmp_path, monkeypatch
):
    profile, manifest_path, manifest = _profile(tmp_path, monkeypatch)
    supervisor = _Supervisor()
    monkeypatch.setattr(
        session_e2e,
        "_handshake_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("authentication rejected")
        ),
    )

    with pytest.raises(
        session_e2e.SessionCleanupSafetyError,
        match="exact retained supervisor was stopped",
    ):
        session_e2e._cleanup_throwaway_session(
            profile,
            manifest_path,
            supervisor=supervisor,
            launch_manifest=manifest,
        )

    assert supervisor.stdin.commands == ["STOP\n"]
    assert supervisor.waits == [session_e2e.CHILD_STOP_TIMEOUT_SECONDS]
    assert profile.is_dir()


def test_exited_supervisor_has_no_pid_fallback(tmp_path, monkeypatch):
    profile, manifest_path, manifest = _profile(tmp_path, monkeypatch)
    supervisor = _Supervisor(returncode=1)
    monkeypatch.setattr(
        session_e2e,
        "_handshake_connection",
        lambda *_args, **_kwargs: pytest.fail(
            "an exited supervisor must not authorize retrospective cleanup"
        ),
    )

    with pytest.raises(
        session_e2e.SessionCleanupSafetyError,
        match="no fallback PID cleanup",
    ):
        session_e2e._cleanup_throwaway_session(
            profile,
            manifest_path,
            supervisor=supervisor,
            launch_manifest=manifest,
        )

    assert supervisor.stdin.commands == []
    assert profile.is_dir()


def test_successfully_exited_supervisor_never_replays_unproven_profile_deletion(
    tmp_path, monkeypatch
):
    profile, manifest_path, manifest = _profile(tmp_path, monkeypatch)
    supervisor = _Supervisor(returncode=0)
    monkeypatch.setattr(
        session_e2e,
        "_endpoint_accepts",
        lambda *_args: False,
    )

    with pytest.raises(
        session_e2e.SessionCleanupSafetyError,
        match="exited before identity-bound cleanup",
    ):
        session_e2e._cleanup_throwaway_session(
            profile,
            manifest_path,
            supervisor=supervisor,
            launch_manifest=manifest,
        )

    assert supervisor.stdin.commands == []
    assert profile.is_dir()


def test_missing_profile_never_prevents_exact_supervisor_shutdown(tmp_path, monkeypatch):
    profile, manifest_path, manifest = _profile(tmp_path, monkeypatch)
    profile.rename(tmp_path / "externally-moved-profile")
    supervisor = _Supervisor()

    session_e2e._cleanup_throwaway_session(
        profile,
        manifest_path,
        supervisor=supervisor,
        launch_manifest=manifest,
    )

    assert supervisor.stdin.commands == ["STOP\n"]
    assert supervisor.waits == [session_e2e.CHILD_STOP_TIMEOUT_SECONDS]


def test_redirected_profile_never_prevents_exact_supervisor_shutdown(
    tmp_path, monkeypatch
):
    profile, manifest_path, manifest = _profile(tmp_path, monkeypatch)
    supervisor = _Supervisor()
    monkeypatch.setattr(session_e2e, "_path_is_redirected", lambda _path: True)

    with pytest.raises(
        session_e2e.SessionCleanupSafetyError,
        match="exact retained supervisor was stopped",
    ):
        session_e2e._cleanup_throwaway_session(
            profile,
            manifest_path,
            supervisor=supervisor,
            launch_manifest=manifest,
        )

    assert supervisor.stdin.commands == ["STOP\n"]
    assert supervisor.waits == [session_e2e.CHILD_STOP_TIMEOUT_SECONDS]
    assert profile.is_dir()


def test_missing_supervisor_preserves_preexisting_profile(tmp_path, monkeypatch):
    profile, manifest_path, manifest = _profile(tmp_path, monkeypatch)

    with pytest.raises(
        session_e2e.SessionCleanupSafetyError,
        match="no retained launch supervisor",
    ):
        session_e2e._cleanup_throwaway_session(
            profile,
            manifest_path,
            launch_manifest=manifest,
        )

    assert profile.is_dir()


def test_interrupted_readiness_stops_retained_supervisor_but_preserves_profile(
    tmp_path, monkeypatch
):
    profile, manifest_path, _manifest = _profile(tmp_path, monkeypatch)
    supervisor = _Supervisor()
    monkeypatch.setattr(
        session_e2e,
        "_handshake_connection",
        lambda *_args, **_kwargs: pytest.fail(
            "readiness-absent cleanup must use only its exact control pipe"
        ),
    )

    with pytest.raises(
        session_e2e.SessionCleanupSafetyError,
        match="exact retained supervisor was stopped",
    ):
        session_e2e._cleanup_throwaway_session(
            profile,
            manifest_path,
            supervisor=supervisor,
            launch_manifest=None,
        )

    assert supervisor.stdin.commands == ["STOP\n"]
    assert supervisor.waits == [session_e2e.CHILD_STOP_TIMEOUT_SECONDS]
    assert profile.is_dir()


def test_pre_yield_readiness_interrupt_uses_registered_supervisor(
    tmp_path, monkeypatch
):
    profile, manifest_path, _manifest = _profile(tmp_path, monkeypatch)
    supervisor = _Supervisor()
    ownership = {"supervisor": supervisor, "launch_manifest": None}

    with pytest.raises(
        session_e2e.SessionCleanupSafetyError,
        match="exact retained supervisor was stopped",
    ):
        with session_e2e._throwaway_cleanup_scope(
            profile, manifest_path, ownership
        ):
            raise RuntimeError("readiness was interrupted")

    assert supervisor.stdin.commands == ["STOP\n"]
    assert profile.is_dir()


def test_log_context_failure_after_spawn_still_uses_registered_supervisor(
    tmp_path, monkeypatch
):
    profile, manifest_path, _manifest = _profile(tmp_path, monkeypatch)
    supervisor = _Supervisor()
    ownership = {"supervisor": None, "launch_manifest": None}

    class FailingLogContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            raise RuntimeError("launcher log close failed")

    with pytest.raises(
        session_e2e.SessionCleanupSafetyError,
        match="exact retained supervisor was stopped",
    ):
        with session_e2e._throwaway_cleanup_scope(
            profile, manifest_path, ownership
        ):
            with FailingLogContext():
                ownership["supervisor"] = supervisor

    assert supervisor.stdin.commands == ["STOP\n"]
    assert supervisor.waits == [session_e2e.CHILD_STOP_TIMEOUT_SECONDS]
    assert profile.is_dir()


def test_popen_return_before_ownership_assignment_uses_local_exact_supervisor(
    tmp_path, monkeypatch
):
    profile, manifest_path, _manifest = _profile(tmp_path, monkeypatch)
    supervisor = _Supervisor()
    ownership = {"supervisor": None, "launch_manifest": None}

    with pytest.raises(
        session_e2e.SessionCleanupSafetyError,
        match="exact retained supervisor was stopped",
    ):
        try:
            with session_e2e._throwaway_cleanup_scope(
                profile, manifest_path, ownership
            ):
                raise KeyboardInterrupt("between Popen and ownership assignment")
        except BaseException:
            if ownership["supervisor"] is None:
                session_e2e._cleanup_throwaway_session(
                    profile,
                    manifest_path,
                    supervisor=supervisor,
                    launch_manifest=None,
                )
            raise

    assert supervisor.stdin.commands == ["STOP\n"]
    assert profile.is_dir()


def test_pre_yield_failure_still_stops_through_registered_supervisor(
    tmp_path, monkeypatch
):
    profile, manifest_path, manifest = _profile(tmp_path, monkeypatch)
    endpoint = {"up": True}
    supervisor = _Supervisor(on_wait=lambda: endpoint.update(up=False))
    monkeypatch.setattr(
        session_e2e,
        "_endpoint_accepts",
        lambda *_args: endpoint["up"],
    )
    monkeypatch.setattr(
        session_e2e,
        "_handshake_connection",
        lambda *_args, **_kwargs: _verified(profile, manifest),
    )
    ownership = {"supervisor": supervisor, "launch_manifest": manifest}

    with pytest.raises(RuntimeError, match="pre-yield validation failed"):
        with session_e2e._throwaway_cleanup_scope(
            profile, manifest_path, ownership
        ):
            raise RuntimeError("pre-yield validation failed")

    assert supervisor.stdin.commands == ["STOP\n"]
    assert not profile.exists()


def test_cleanup_rejects_redirected_profile(tmp_path, monkeypatch):
    target = tmp_path / session_e2e.PROFILE_NAME
    target.mkdir()
    monkeypatch.setattr(session_e2e, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(session_e2e, "_path_is_redirected", lambda _path: True)

    with pytest.raises(
        session_e2e.SessionCleanupSafetyError,
        match="redirected throwaway profile",
    ):
        session_e2e._remove_throwaway_profile(target)

    assert target.is_dir()
