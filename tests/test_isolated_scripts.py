"""Focused tests for the manifest-driven isolated FreeCAD launch scripts."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import uuid

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
        requests = []

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
    freecad = tmp_path / "build" / "release" / "bin" / "FreeCAD.exe"
    freecad.parent.mkdir(parents=True)
    freecad.touch()
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

        @staticmethod
        def poll():
            return None

    class Proxy:
        @staticmethod
        def get_instance_info():
            return _runtime_info(profile)

        @staticmethod
        def handshake_v2(request):
            return {"client_nonce": request["client_nonce"], "proof": "not-a-proof"}

    writes = []
    monkeypatch.setattr(launcher, "_repo_root", lambda: tmp_path)
    reservation = SimpleNamespace(closed=False)

    def close_reservation():
        reservation.closed = True

    reservation.close = close_reservation
    monkeypatch.setattr(launcher, "_reserve_endpoint", lambda *_args: reservation)
    monkeypatch.setattr(
        launcher,
        "_load_parent_start_freecad",
        lambda: SimpleNamespace(
            _launch_details=lambda executable, extra: (
                [str(executable), *extra],
                str(tmp_path),
                {},
            )
        ),
    )
    def spawn(*_args, **_kwargs):
        assert reservation.closed is True
        return Process()

    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    monkeypatch.setattr(launcher.xmlrpc.client, "ServerProxy", lambda *args, **kwargs: Proxy())
    monkeypatch.setattr(
        launcher, "_write_manifest", lambda profile_path, value: writes.append(value)
    )
    monkeypatch.setattr(sys, "argv", ["start_freecad_isolated.py"])

    assert launcher.main() == 1
    assert writes == []


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
    freecad = tmp_path / "build" / "release" / "bin" / "FreeCAD.exe"
    freecad.parent.mkdir(parents=True)
    freecad.touch()
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


@pytest.mark.parametrize("script_name", ["start_freecad_isolated.py", "setup_cursor_mcp_isolated.py"])
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


@pytest.mark.parametrize("script_name", ["start_freecad_isolated.py", "setup_cursor_mcp_isolated.py"])
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

    with pytest.raises(SystemExit, match="extra=.*unexpected_downgrade_flag"):
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
