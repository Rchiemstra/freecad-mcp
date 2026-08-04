"""Configuration migration and fail-closed transport-policy tests."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

SETTINGS_MODULE = (
    Path(__file__).resolve().parents[1]
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "settings.py"
)


@pytest.fixture
def isolated_document_lock_runtime():
    """Keep process-lifetime lease mode and registries local to each test."""

    from addon.FreeCADMCP import document_lock

    previous_mode = document_lock.get_runtime_lease_mode()
    yield
    document_lock.reset_registry_for_tests()
    if previous_mode is not None:
        document_lock.configure_runtime_lease_mode(previous_mode)


class _Console:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def PrintWarning(self, message: str) -> None:
        self.warnings.append(message)

    def PrintError(self, message: str) -> None:
        self.errors.append(message)


def _load_settings(tmp_path: Path, monkeypatch):
    console = _Console()
    freecad = SimpleNamespace(
        Console=console,
        getUserAppDataDir=lambda: str(tmp_path),
    )
    monkeypatch.setitem(sys.modules, "FreeCAD", freecad)
    name = f"freecad_mcp_settings_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SETTINGS_MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, console


def _write(tmp_path: Path, value) -> None:
    (tmp_path / "freecad_mcp_settings.json").write_text(
        json.dumps(value), encoding="utf-8"
    )


def test_new_ordinary_profile_defaults_to_observe(tmp_path, monkeypatch):
    settings, _console = _load_settings(tmp_path, monkeypatch)

    loaded = settings.load_settings()

    assert loaded["document_lease_mode"] == "observe"
    assert loaded["enable_document_lock"] is True
    assert loaded["document_lock_enforcement"] is False
    assert loaded["rpc_bind_host"] == "127.0.0.1"
    assert loaded["remote_enabled"] is False
    assert loaded["persist_task_summary_in_sidecar"] is False


def test_profile_secret_is_created_and_rehardened(tmp_path, monkeypatch):
    settings, _console = _load_settings(tmp_path, monkeypatch)

    _current, secret_path = settings.ensure_profile_secret({})
    secret = Path(secret_path)
    assert len(secret.read_bytes()) == 32
    if os.name != "nt":
        assert secret.stat().st_mode & 0o077 == 0
        secret.chmod(0o644)
        settings.ensure_profile_secret({"auth_secret_file": str(secret)})
        assert secret.stat().st_mode & 0o077 == 0


def test_profile_secret_accepts_pathlike_and_persists_string(tmp_path, monkeypatch):
    settings, _console = _load_settings(tmp_path, monkeypatch)
    secret = tmp_path / "nested" / "profile.secret"

    current, returned_path = settings.ensure_profile_secret(
        {"auth_secret_file": secret}
    )

    assert secret.is_file()
    assert current["auth_secret_file"] == str(secret)
    assert returned_path == str(secret)
    persisted = json.loads(
        (tmp_path / "freecad_mcp_settings.json").read_text(encoding="utf-8")
    )
    assert persisted["auth_secret_file"] == str(secret)


@pytest.mark.parametrize(
    ("enabled", "enforced", "expected"),
    [
        (True, True, "enforce"),
        (True, False, "observe"),
        (False, True, "off"),
        (False, False, "off"),
    ],
)
def test_legacy_boolean_migration_preserves_policy(
    tmp_path, monkeypatch, enabled, enforced, expected
):
    settings, _console = _load_settings(tmp_path, monkeypatch)
    _write(
        tmp_path,
        {
            "enable_document_lock": enabled,
            "document_lock_enforcement": enforced,
        },
    )

    loaded = settings.load_settings()

    assert loaded["document_lease_mode"] == expected
    assert loaded["enable_document_lock"] is (expected != "off")
    assert loaded["document_lock_enforcement"] is (expected == "enforce")
    persisted = json.loads(
        (tmp_path / "freecad_mcp_settings.json").read_text(encoding="utf-8")
    )
    assert persisted["document_lease_mode"] == expected


def test_existing_empty_settings_file_preserves_legacy_off(tmp_path, monkeypatch):
    settings, _console = _load_settings(tmp_path, monkeypatch)
    _write(tmp_path, {})

    assert settings.load_settings()["document_lease_mode"] == "off"


@pytest.mark.parametrize("payload", [{"document_lease_mode": "typo"}, []])
def test_invalid_persisted_configuration_fails_closed(tmp_path, monkeypatch, payload):
    settings, console = _load_settings(tmp_path, monkeypatch)
    _write(tmp_path, payload)

    loaded = settings.load_settings()

    assert loaded["document_lease_mode"] == "enforce"
    assert loaded["document_lock_enforcement"] is True
    assert loaded["auto_start_rpc"] is False
    assert loaded["remote_enabled"] is False
    assert loaded["_configuration_error"]
    assert console.warnings

    original = (tmp_path / "freecad_mcp_settings.json").read_text(encoding="utf-8")
    settings.save_settings(loaded)
    assert (tmp_path / "freecad_mcp_settings.json").read_text(
        encoding="utf-8"
    ) == original
    assert console.errors


def test_security_boolean_strings_are_not_truthy_configuration(tmp_path, monkeypatch):
    settings, _console = _load_settings(tmp_path, monkeypatch)
    _write(
        tmp_path,
        {
            "document_lease_mode": "enforce",
            "remote_enabled": True,
            "allow_authenticated_remote_without_transport_security": "false",
        },
    )

    loaded = settings.load_settings()

    assert loaded["_configuration_error"].startswith(
        "allow_authenticated_remote_without_transport_security must"
    )
    assert loaded["remote_enabled"] is False


def test_sidecar_task_summary_opt_in_requires_a_boolean(tmp_path, monkeypatch):
    settings, _console = _load_settings(tmp_path, monkeypatch)
    _write(
        tmp_path,
        {
            "document_lease_mode": "observe",
            "persist_task_summary_in_sidecar": "false",
        },
    )

    loaded = settings.load_settings()

    assert loaded["document_lease_mode"] == "enforce"
    assert loaded["persist_task_summary_in_sidecar"] is False
    assert "persist_task_summary_in_sidecar must" in loaded["_configuration_error"]


def test_legacy_boolean_strings_do_not_change_migration_policy(tmp_path, monkeypatch):
    settings, _console = _load_settings(tmp_path, monkeypatch)
    _write(
        tmp_path,
        {
            "enable_document_lock": "false",
            "document_lock_enforcement": "false",
        },
    )

    loaded = settings.load_settings()

    assert loaded["document_lease_mode"] == "enforce"
    assert "enable_document_lock must" in loaded["_configuration_error"]


def test_enforce_mode_rejects_plain_non_loopback_without_explicit_override(
    tmp_path, monkeypatch
):
    settings, _console = _load_settings(tmp_path, monkeypatch)
    policy = dict(settings.DEFAULT_SETTINGS)
    policy.update(
        {
            "document_lease_mode": "enforce",
            "profile_instance_id": str(uuid.uuid4()),
            "remote_enabled": True,
            "rpc_bind_host": "0.0.0.0",
        }
    )

    with pytest.raises(settings.SettingsPolicyError, match="plain non-loopback"):
        settings.resolve_rpc_bind_host(policy)

    policy["allow_authenticated_remote_without_transport_security"] = True
    assert settings.resolve_rpc_bind_host(policy) == "0.0.0.0"


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("127.42.0.9", True),
        ("::1", True),
        ("[::1]", True),
        ("LOCALHOST.", True),
        ("0.0.0.0", False),
        ("192.0.2.1", False),
        ("example.invalid", False),
    ],
)
def test_loopback_classification_is_explicit(tmp_path, monkeypatch, host, expected):
    settings, _console = _load_settings(tmp_path, monkeypatch)
    assert settings.is_loopback_host(host) is expected


def test_rpc_start_rejects_configuration_error_before_binding(monkeypatch):
    from addon.FreeCADMCP.rpc_server import rpc_server

    app_thread = object()
    dispatcher = SimpleNamespace(deleteLater=lambda: None)
    bound = []
    monkeypatch.setattr(rpc_server, "rpc_server_instance", None)
    monkeypatch.setattr(
        rpc_server.QtWidgets.QApplication,
        "instance",
        staticmethod(lambda: SimpleNamespace(thread=lambda: app_thread)),
    )
    monkeypatch.setattr(
        rpc_server.QtCore.QThread,
        "currentThread",
        staticmethod(lambda: app_thread),
    )
    monkeypatch.setattr(
        rpc_server.FreeCADGui, "getMainWindow", lambda: None, raising=False
    )
    monkeypatch.setattr(rpc_server, "GuiDispatcher", lambda _parent: dispatcher)
    monkeypatch.setattr(
        rpc_server,
        "load_settings",
        lambda: {"_configuration_error": "unknown document_lease_mode"},
    )
    monkeypatch.setattr(
        rpc_server,
        "FilteredXMLRPCServer",
        lambda *args, **kwargs: bound.append((args, kwargs)),
    )

    result = rpc_server.start_rpc_server()

    assert "refused invalid" in result
    assert bound == []


def _prepare_authenticated_rpc_start(monkeypatch, *, session_manager):
    from addon.FreeCADMCP.rpc_server import rpc_server

    profile_id = str(uuid.uuid4())
    app_thread = object()
    dispatcher = SimpleNamespace(deleteLater=lambda: None)
    lease_service = SimpleNamespace(
        list_records=lambda: [],
        has_unresolved_owner=lambda _owner: False,
    )
    replay_cache = SimpleNamespace(set_owner_lease_predicate=lambda _predicate: None)

    class _Server:
        server_address = ("127.0.0.1", 19875)

        def register_instance(self, instance):
            self.instance = instance

        def serve_forever(self):
            pass

        def server_close(self):
            pass

    class _Thread:
        def __init__(self, *, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    settings = {
        "document_lease_mode": "observe",
        "profile_instance_id": profile_id,
        "auth_secret_file": "profile.secret",
        "rpc_port": 0,
        "remote_enabled": False,
        "allowed_ips": "127.0.0.1",
    }
    runtime_identity = SimpleNamespace(
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=123,
        freecad_process_started_at="2026-07-22T00:00:00Z",
        boot_id="boot-test",
    )
    manifest = SimpleNamespace(
        protocol_version=2,
        features=("authenticated_rpc_v2",),
    )

    monkeypatch.setattr(rpc_server, "rpc_server_instance", None)
    monkeypatch.setattr(rpc_server, "rpc_server_thread", None)
    monkeypatch.setattr(rpc_server, "gui_dispatcher", None)
    monkeypatch.setattr(rpc_server, "worker_manager", None)
    monkeypatch.setattr(rpc_server, "rpc_session_manager", None)
    monkeypatch.setattr(rpc_server, "rpc_runtime_manifest", None)
    monkeypatch.setattr(rpc_server, "rpc_server_actual_endpoint", None)
    monkeypatch.setattr(rpc_server, "rpc_server_runtime_id", "")
    monkeypatch.setattr(rpc_server, "rpc_server_started_at", "")
    monkeypatch.setattr(rpc_server, "_addon_runtime", None)
    monkeypatch.setattr(rpc_server, "document_lease_service", lease_service)
    monkeypatch.setattr(rpc_server, "rpc_request_replay_cache", replay_cache)
    monkeypatch.setattr(
        rpc_server.QtWidgets.QApplication,
        "instance",
        staticmethod(lambda: SimpleNamespace(thread=lambda: app_thread)),
    )
    monkeypatch.setattr(
        rpc_server.QtCore.QThread,
        "currentThread",
        staticmethod(lambda: app_thread),
    )
    monkeypatch.setattr(
        rpc_server.FreeCADGui, "getMainWindow", lambda: None, raising=False
    )
    monkeypatch.setattr(rpc_server, "GuiDispatcher", lambda _parent: dispatcher)
    monkeypatch.setattr(rpc_server, "load_settings", lambda: dict(settings))
    monkeypatch.setattr(rpc_server, "configure_parts_library_path", lambda _path: None)
    monkeypatch.setattr(rpc_server, "_freecad_version_parts", lambda: ("1", "1", "0", "r"))
    monkeypatch.setattr(rpc_server, "_profile_fingerprint", lambda: "profile-hash")
    monkeypatch.setattr(rpc_server.FreeCAD, "getUserAppDataDir", lambda: "")
    monkeypatch.setattr(
        rpc_server.FreeCAD, "getHomePath", lambda: "", raising=False
    )
    monkeypatch.setattr(rpc_server.FreeCAD, "listDocuments", lambda: {})
    monkeypatch.setattr(
        rpc_server, "WorkerManager", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        rpc_server, "initialize_document_lease_runtime", lambda _settings: lease_service
    )
    monkeypatch.setattr(rpc_server, "resolve_rpc_bind_host", lambda _settings: "127.0.0.1")
    monkeypatch.setattr(rpc_server, "FilteredXMLRPCServer", lambda *_args, **_kwargs: _Server())
    monkeypatch.setattr(
        rpc_server,
        "_require_authenticated_lease_runtime",
        lambda _profile_id: runtime_identity,
    )
    monkeypatch.setattr(rpc_server, "make_runtime_manifest", lambda **_kwargs: manifest)
    monkeypatch.setattr(rpc_server, "SessionManager", session_manager)
    monkeypatch.setattr(rpc_server.threading, "Thread", _Thread)
    return rpc_server


def test_session_manager_built_when_configured(monkeypatch):
    built = []

    def build_session_manager(*, manifest, secret):
        manager = SimpleNamespace(manifest=manifest, secret=secret)
        built.append(manager)
        return manager

    rpc_server = _prepare_authenticated_rpc_start(
        monkeypatch, session_manager=build_session_manager
    )
    monkeypatch.setattr(rpc_server, "load_profile_secret", lambda _path: b"x" * 32)

    result = rpc_server.start_rpc_server()

    assert result == "RPC Server started at 127.0.0.1:19875."
    assert rpc_server.rpc_session_manager is built[0]
    assert built[0].manifest.protocol_version == 2


def test_v2_init_failure_is_visible_in_observe_mode(monkeypatch):
    rpc_server = _prepare_authenticated_rpc_start(
        monkeypatch,
        session_manager=lambda **_kwargs: pytest.fail(
            "SessionManager must not be reached"
        ),
    )
    monkeypatch.setattr(
        rpc_server,
        "load_profile_secret",
        lambda _path: (_ for _ in ()).throw(
            RuntimeError("trusted boot identity is unavailable")
        ),
    )

    result = rpc_server.start_rpc_server()

    assert "WARNING: authenticated RPC protocol v2 is unavailable" in result
    assert "trusted boot identity is unavailable" in result
    assert "profile_instance_id" in result
    assert rpc_server.rpc_session_manager is None


def test_rpc_stop_preserves_addon_process_lease_authority(monkeypatch):
    """Restarting the transport must not orphan UUIDs or active sidecars."""

    from addon.FreeCADMCP.rpc_server import rpc_server

    class _Server:
        def begin_shutdown(self):
            pass

        def shutdown(self):
            pass

        def server_close(self):
            pass

    class _Dispatcher:
        def stop_accepting(self):
            pass

        def deleteLater(self):
            pass

    identity_service = object()
    lease_service = object()
    save_service = object()
    monkeypatch.setattr(rpc_server, "rpc_server_instance", _Server())
    monkeypatch.setattr(rpc_server, "rpc_server_thread", None)
    monkeypatch.setattr(rpc_server, "gui_dispatcher", _Dispatcher())
    monkeypatch.setattr(rpc_server, "worker_manager", None)
    monkeypatch.setattr(rpc_server, "lease_watchdog_thread", None)
    monkeypatch.setattr(rpc_server, "document_identity_service", identity_service)
    monkeypatch.setattr(rpc_server, "document_lease_service", lease_service)
    monkeypatch.setattr(rpc_server, "save_service", save_service)

    assert "stopped" in rpc_server.stop_rpc_server().lower()
    assert rpc_server.document_identity_service is identity_service
    assert rpc_server.document_lease_service is lease_service
    assert rpc_server.save_service is save_service


def test_document_lease_runtime_outlives_transport_and_upgrades_when_clean(
    monkeypatch,
    isolated_document_lock_runtime,
):
    from addon.FreeCADMCP.rpc_server import rpc_server

    monkeypatch.setattr(rpc_server, "document_identity_service", None)
    monkeypatch.setattr(rpc_server, "document_lease_service", None)
    monkeypatch.setattr(rpc_server, "document_lease_runtime_policy", None)
    monkeypatch.setattr(rpc_server, "document_lease_runtime_mode", None)
    monkeypatch.setattr(rpc_server, "save_service", None)
    monkeypatch.setattr(rpc_server.FreeCAD, "listDocuments", lambda: {})
    monkeypatch.setattr(rpc_server, "_ensure_lease_watchdog_running", lambda: None)

    first = rpc_server.initialize_document_lease_runtime(
        {
            "document_lease_mode": "observe",
            "allow_network_sidecar": False,
            "persist_task_summary_in_sidecar": False,
        }
    )
    identities = rpc_server.document_identity_service
    assert first.sidecar_store.strict_permissions is False
    assert first.sidecar_store.persist_task_summary is False
    assert first._local_runtime_identity.addon_runtime_id == (
        rpc_server._ADDON_RUNTIME_ID
    )
    assert first._local_runtime_identity.freecad_pid == os.getpid()
    assert first._process_liveness_probe is rpc_server._probe_process_liveness

    second = rpc_server.initialize_document_lease_runtime(
        {
            "document_lease_mode": "observe",
            "allow_network_sidecar": False,
            "persist_task_summary_in_sidecar": False,
        }
    )
    assert second is first
    assert rpc_server.document_identity_service is identities

    upgraded = rpc_server.initialize_document_lease_runtime(
        {
            "document_lease_mode": "enforce",
            "allow_network_sidecar": False,
            "persist_task_summary_in_sidecar": True,
        }
    )
    assert upgraded is not first
    assert upgraded.sidecar_store.strict_permissions is True
    assert upgraded.sidecar_store.persist_task_summary is True
    assert rpc_server.document_identity_service is identities


def test_document_lease_runtime_rejects_live_mode_downgrade(
    monkeypatch,
    isolated_document_lock_runtime,
):
    from addon.FreeCADMCP.rpc_server import rpc_server

    service = SimpleNamespace(
        list_effective_records=lambda: [{"lease": {"state": "LOCKED_IDLE"}}],
        list_records=lambda: [{"lease": {"state": "LOCKED_IDLE"}}],
    )
    monkeypatch.setattr(rpc_server, "document_lease_service", service)
    monkeypatch.setattr(rpc_server, "document_identity_service", object())
    monkeypatch.setattr(
        rpc_server, "document_lease_runtime_policy", (True, False, False)
    )
    monkeypatch.setattr(rpc_server, "document_lease_runtime_mode", "enforce")

    with pytest.raises(rpc_server.SettingsPolicyError, match="mode cannot change"):
        rpc_server.initialize_document_lease_runtime(
            {
                "document_lease_mode": "observe",
                "allow_network_sidecar": False,
                "persist_task_summary_in_sidecar": False,
            }
        )

def test_runtime_watchdog_starts_without_rpc_auto_start_and_is_idempotent(
    monkeypatch,
    isolated_document_lock_runtime,
):
    from addon.FreeCADMCP.rpc_server import rpc_server

    rpc_server.shutdown_document_lease_runtime(timeout=1.0)
    monkeypatch.setattr(rpc_server, "document_identity_service", None)
    monkeypatch.setattr(rpc_server, "document_lease_service", None)
    monkeypatch.setattr(rpc_server, "document_lease_runtime_policy", None)
    monkeypatch.setattr(rpc_server, "document_lease_runtime_mode", None)
    monkeypatch.setattr(rpc_server, "save_service", None)
    monkeypatch.setattr(rpc_server.FreeCAD, "listDocuments", lambda: {})
    settings = {
        "auto_start_rpc": False,
        "document_lease_mode": "observe",
        "allow_network_sidecar": False,
        "persist_task_summary_in_sidecar": False,
    }

    try:
        service = rpc_server.initialize_document_lease_runtime(settings)
        first = rpc_server.lease_watchdog_thread
        assert first is not None and first.is_alive()
        assert rpc_server.rpc_server_instance is None

        assert rpc_server.initialize_document_lease_runtime(settings) is service
        assert rpc_server.lease_watchdog_thread is first
        assert "not running" in rpc_server.stop_rpc_server().lower()
        assert rpc_server.lease_watchdog_thread is first
        assert first.is_alive()
    finally:
        assert rpc_server.shutdown_document_lease_runtime(timeout=1.0)


def test_listener_stop_preserves_watchdog_stale_progression_and_records(
    monkeypatch,
):
    from addon.FreeCADMCP.rpc_server import rpc_server

    class _Server:
        def begin_shutdown(self):
            pass

        def shutdown(self):
            pass

        def server_close(self):
            pass

    class _Dispatcher:
        def stop_accepting(self):
            pass

        def deleteLater(self):
            pass

    class _Service:
        def __init__(self):
            self.calls = 0
            self.progressed = threading.Event()
            self.records = [{"lease": {"state": "LOCKED_IDLE"}}]

        def mark_expired_stale(self):
            self.calls += 1
            self.progressed.set()
            return []

        def list_records(self):
            return list(self.records)

    rpc_server.shutdown_document_lease_runtime(timeout=1.0)
    service = _Service()
    identity_service = object()
    monkeypatch.setattr(rpc_server, "document_lease_service", service)
    monkeypatch.setattr(rpc_server, "document_identity_service", identity_service)
    monkeypatch.setattr(rpc_server, "rpc_server_instance", _Server())
    monkeypatch.setattr(rpc_server, "rpc_server_thread", None)
    monkeypatch.setattr(rpc_server, "gui_dispatcher", _Dispatcher())
    monkeypatch.setattr(rpc_server, "worker_manager", None)

    try:
        watchdog = rpc_server._ensure_lease_watchdog_running(0.01)
        assert service.progressed.wait(1.0)
        before = service.calls

        assert "stopped" in rpc_server.stop_rpc_server().lower()
        assert rpc_server.document_lease_service is service
        assert rpc_server.document_identity_service is identity_service
        assert service.list_records() == [{"lease": {"state": "LOCKED_IDLE"}}]
        assert rpc_server.lease_watchdog_thread is watchdog
        assert watchdog.is_alive()
        assert not rpc_server.lease_watchdog_stop.is_set()

        deadline = time.monotonic() + 1.0
        while service.calls <= before and time.monotonic() < deadline:
            time.sleep(0.01)
        assert service.calls > before
        assert rpc_server._ensure_lease_watchdog_running(0.01) is watchdog
    finally:
        assert rpc_server.shutdown_document_lease_runtime(timeout=1.0)


def test_local_runtime_identity_uses_profile_and_conservative_process_evidence(
    monkeypatch,
):
    from addon.FreeCADMCP.document_lease import ProcessLivenessEvidence
    from addon.FreeCADMCP.rpc_server import rpc_server

    profile_id = "20acb401-64c1-4438-87e4-2fa7036d4d28"
    assert rpc_server._probe_process_liveness(0).exists is None
    monkeypatch.setattr(rpc_server.os, "getpid", lambda: 321)
    monkeypatch.setattr(rpc_server.platform, "node", lambda: "test-host")
    monkeypatch.setattr(
        rpc_server, "rpc_server_runtime_id", rpc_server._ADDON_RUNTIME_ID
    )
    monkeypatch.setattr(rpc_server, "_trusted_boot_identity", lambda: "boot-1")
    monkeypatch.setattr(
        rpc_server,
        "_probe_process_liveness",
        lambda pid: ProcessLivenessEvidence(
            exists=True,
            process_started_at="2026-07-22T10:00:00Z" if pid == 321 else None,
        ),
    )

    identity = rpc_server._make_local_runtime_identity(
        {"profile_instance_id": profile_id}
    )

    assert identity.addon_profile_id == profile_id
    assert identity.addon_runtime_id == rpc_server._ADDON_RUNTIME_ID
    assert identity.freecad_pid == 321
    assert identity.freecad_process_started_at == "2026-07-22T10:00:00Z"
    assert identity.boot_id == "boot-1"
    assert rpc_server._boot_identity() == identity.boot_id
    assert identity.hostname == "test-host"
    monkeypatch.setattr(
        rpc_server,
        "document_lease_service",
        SimpleNamespace(local_runtime_identity=identity),
    )
    assert rpc_server._require_authenticated_lease_runtime(profile_id) is identity

    unavailable = SimpleNamespace(**identity.__dict__)
    unavailable.boot_id = ""
    rpc_server.document_lease_service.local_runtime_identity = unavailable
    with pytest.raises(RuntimeError, match="identity is unavailable"):
        rpc_server._require_authenticated_lease_runtime(profile_id)


def test_boot_identity_non_empty():
    from addon.FreeCADMCP.rpc_server import rpc_server

    assert rpc_server._trusted_boot_identity()


def test_ntquery_exact_buffer_size(monkeypatch):
    import ctypes

    from addon.FreeCADMCP.rpc_server import rpc_server

    class _MissingProcPath:
        def __init__(self, _path):
            pass

        def read_text(self, **_kwargs):
            raise OSError("procfs unavailable")

    sizes = []

    def nt_query(_info_class, buffer, size, returned):
        sizes.append(size)
        returned._obj.value = 48
        ctypes.c_int64.from_buffer(buffer).value = 0x1234
        return 0

    monkeypatch.setattr(rpc_server, "Path", _MissingProcPath)
    monkeypatch.setattr(rpc_server.os, "name", "nt")
    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(
            ntdll=SimpleNamespace(NtQuerySystemInformation=nt_query)
        ),
        raising=False,
    )

    assert rpc_server._trusted_boot_identity() == "windows-boot:1234"
    assert sizes == [48]


def test_document_lease_runtime_does_not_coerce_task_summary_opt_in(
    isolated_document_lock_runtime,
):
    from addon.FreeCADMCP.rpc_server import rpc_server

    with pytest.raises(
        rpc_server.SettingsPolicyError,
        match="persist_task_summary_in_sidecar must",
    ):
        rpc_server.initialize_document_lease_runtime(
            {
                "document_lease_mode": "observe",
                "persist_task_summary_in_sidecar": "false",
            }
        )


def test_remote_gui_toggle_refuses_plain_transport_in_enforce_mode(monkeypatch):
    from addon.FreeCADMCP.rpc_server import commands

    policy = {
        "document_lease_mode": "enforce",
        "remote_enabled": False,
        "rpc_bind_host": "127.0.0.1",
        "allow_authenticated_remote_without_transport_security": False,
    }
    saved = []
    warnings = []
    monkeypatch.setattr(commands, "load_settings", lambda: dict(policy))
    monkeypatch.setattr(commands, "save_settings", lambda value: saved.append(value))
    monkeypatch.setattr(
        commands.FreeCAD.Console,
        "PrintWarning",
        lambda message: warnings.append(message),
    )

    commands.ToggleRemoteConnectionsCommand().Activated(True)

    assert saved == []
    assert warnings and "HMAC does not encrypt" in warnings[0]


def test_remote_gui_toggle_preserves_legacy_observe_behavior(monkeypatch):
    from addon.FreeCADMCP.rpc_server import commands

    policy = {
        "document_lease_mode": "observe",
        "remote_enabled": False,
        "rpc_bind_host": "127.0.0.1",
        "allowed_ips": "127.0.0.1",
        "allow_authenticated_remote_without_transport_security": False,
    }
    saved = []
    monkeypatch.setattr(commands, "load_settings", lambda: dict(policy))
    monkeypatch.setattr(commands, "save_settings", lambda value: saved.append(value))

    commands.ToggleRemoteConnectionsCommand().Activated(True)

    assert saved[0]["remote_enabled"] is True
    assert saved[0]["rpc_bind_host"] == "0.0.0.0"
