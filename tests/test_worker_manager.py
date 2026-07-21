"""Worker build identity, quota, artifact, and security admission tests."""

from __future__ import annotations

import os
import time
from types import SimpleNamespace

import pytest
import FreeCADGui


if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server import worker_manager as manager_module
from addon.FreeCADMCP.rpc_server.rpc_server import FreeCADRPC, _DEFAULT_SETTINGS
from addon.FreeCADMCP.rpc_server import parts_library
from addon.FreeCADMCP.rpc_server.worker_manager import (
    VERSION_PROBE_TIMEOUT_SECONDS,
    WorkerManager,
    WorkerRuntime,
    WorkerVersionMismatch,
    require_compatible_builds,
)
from addon.FreeCADMCP.rpc_server.worker_protocol import (
    MAX_CODE_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_RESULT_BYTES,
    ProtocolError,
    clamp_timeout,
    read_json_limited,
    validate_job,
)


def _runtime(version=("1", "2", "3", ""), configured_path=""):
    return WorkerRuntime("FreeCAD", "/missing", version, configured_path)


def test_exact_stable_build_match():
    require_compatible_builds(("1", "2", "3", ""), ("1", "2", "3", ""))


@pytest.mark.parametrize(
    "gui,worker",
    [
        (("1", "2", "3", ""), ("1", "2", "4", "")),
        (("1", "2", "3", "rev-a"), ("1", "2", "3", "rev-b")),
        (("1", "2", "3", "rev-a"), ("1", "2", "3", "")),
        (("1", "2", "", ""), ("1", "2", "3", "")),
    ],
)
def test_incompatible_or_ambiguous_build_identity_is_rejected(gui, worker):
    with pytest.raises(WorkerVersionMismatch):
        require_compatible_builds(gui, worker)


def test_configured_executable_from_different_build_is_rejected(tmp_path, monkeypatch):
    executable = tmp_path / "Different FreeCADCmd"
    executable.write_text("probe", encoding="utf-8")
    manager = WorkerManager(
        _runtime(("1", "2", "3", "gui-rev"), str(executable)),
        "addon/FreeCADMCP/rpc_server",
        temp_root=tmp_path / "workers",
    )
    monkeypatch.setattr(manager, "_candidate_paths", lambda: [executable])
    monkeypatch.setattr(
        manager, "_probe_version", lambda _path: ("1", "2", "3", "other-rev")
    )
    try:
        with pytest.raises(WorkerVersionMismatch):
            manager.discover_executable()
    finally:
        manager.stop()


def test_version_probe_timeout_has_operational_headroom():
    assert VERSION_PROBE_TIMEOUT_SECONDS == 15


def test_probe_version_passes_configured_timeout(tmp_path, monkeypatch):
    executable = tmp_path / "FreeCADCmd"
    executable.write_text("probe", encoding="utf-8")
    manager = WorkerManager(
        _runtime(("1", "2", "3", "")),
        "addon/FreeCADMCP/rpc_server",
        temp_root=tmp_path / "workers",
    )
    seen = {}

    def _fake_run(*_args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return SimpleNamespace(
            returncode=0,
            stdout="FreeCAD 1.2.3 Revision: ",
            stderr="",
        )

    monkeypatch.setattr(manager_module.subprocess, "run", _fake_run)
    try:
        assert manager._probe_version(executable)[:3] == ("1", "2", "3")
        assert seen["timeout"] == VERSION_PROBE_TIMEOUT_SECONDS
    finally:
        manager.stop()


def test_successful_discovery_clears_stale_last_error(tmp_path, monkeypatch):
    executable = tmp_path / "FreeCADCmd"
    executable.write_text("probe", encoding="utf-8")
    manager = WorkerManager(
        _runtime(("1", "2", "3", "")),
        "addon/FreeCADMCP/rpc_server",
        temp_root=tmp_path / "workers",
    )
    manager._last_error = f"{executable}: --version timed out after 5 seconds"
    monkeypatch.setattr(manager, "_candidate_paths", lambda: [executable])
    monkeypatch.setattr(
        manager, "_probe_version", lambda _path: ("1", "2", "3", "")
    )
    try:
        discovered = manager.discover_executable()
        assert discovered == executable.resolve()
        status = manager.status()
        assert status["available"] is True
        assert status["last_error"] is None
    finally:
        manager.stop()


def test_remote_arbitrary_execution_is_disabled_by_default():
    assert _DEFAULT_SETTINGS["allow_remote_execute_code"] is False
    result = FreeCADRPC(allow_execute_code=False).execute_code("print('blocked')")
    assert result["error_code"] == "remote_execute_code_disabled"


def test_code_and_manifest_limits(tmp_path):
    manager = WorkerManager(
        _runtime(), "addon/FreeCADMCP/rpc_server", temp_root=tmp_path / "workers"
    )
    workspace = manager.create_workspace()
    try:
        result = manager.execute("x" * (MAX_CODE_BYTES + 1), {}, {}, workspace)
        assert result["error_code"] == "resource_limit_exceeded"
        job = {
            "schema_version": 1,
            "job_id": "large-manifest",
            "kind": "execute_code",
            "result_path": str(tmp_path / "result.json"),
            "code": "print(1)",
            "options": {},
            "artifact_directory": str(tmp_path / "artifacts"),
            "snapshot": {"documents": [{"padding": "x" * (MAX_MANIFEST_BYTES + 1)}]},
        }
        with pytest.raises(ProtocolError, match="manifest"):
            validate_job(job)
    finally:
        manager.stop()


def test_result_json_limit(tmp_path):
    result = tmp_path / "result.json"
    with result.open("wb") as handle:
        handle.truncate(MAX_RESULT_BYTES + 1)
    with pytest.raises(ProtocolError, match="exceeds"):
        read_json_limited(result)


def test_runtime_bounds_are_enforced():
    with pytest.raises(ProtocolError):
        clamp_timeout(0)
    with pytest.raises(ProtocolError):
        clamp_timeout(901)


def test_artifact_individual_and_aggregate_limits(tmp_path, monkeypatch):
    manager = WorkerManager(
        _runtime(), "addon/FreeCADMCP/rpc_server", temp_root=tmp_path / "workers"
    )
    monkeypatch.setattr(manager_module, "MAX_ARTIFACT_BYTES", 10)
    monkeypatch.setattr(manager_module, "MAX_ARTIFACTS_TOTAL_BYTES", 10)
    try:
        staging = tmp_path / "staging-individual"
        staging.mkdir()
        too_large = staging / "large.step"
        too_large.write_bytes(b"x" * 11)
        with pytest.raises(ProtocolError, match="individual"):
            manager._promote_artifacts(
                [{"path": str(too_large)}], staging, "individual"
            )

        aggregate = tmp_path / "staging-aggregate"
        aggregate.mkdir()
        first = aggregate / "one.step"
        second = aggregate / "two.step"
        first.write_bytes(b"x" * 6)
        second.write_bytes(b"x" * 6)
        with pytest.raises(ProtocolError, match="total"):
            manager._promote_artifacts(
                [{"path": str(first)}, {"path": str(second)}], aggregate, "aggregate"
            )
    finally:
        manager.stop()


def test_artifact_path_escape_and_expiry(tmp_path):
    manager = WorkerManager(
        _runtime(), "addon/FreeCADMCP/rpc_server", temp_root=tmp_path / "workers"
    )
    try:
        staging = tmp_path / "staging"
        staging.mkdir()
        outside = tmp_path / "outside.step"
        outside.write_bytes(b"step")
        with pytest.raises(ProtocolError, match="escaped"):
            manager._promote_artifacts([{"path": str(outside)}], staging, "escape")

        expired = manager.artifact_root / "expired"
        expired.mkdir(parents=True)
        old = time.time() - 3700
        os.utime(expired, (old, old))
        workspace = manager.create_workspace()
        assert not expired.exists()
        assert workspace.exists()
    finally:
        manager.stop()


def test_cached_parts_path_avoids_background_freecad_path_lookup(tmp_path, monkeypatch):
    library = tmp_path / "Mod" / "parts_library"
    library.mkdir(parents=True)
    (library / "Part.FCStd").write_bytes(b"test")
    parts_library.configure_parts_library_path(str(tmp_path))
    monkeypatch.setattr(
        parts_library.FreeCAD,
        "getUserAppDataDir",
        lambda: (_ for _ in ()).throw(
            AssertionError("background handler queried FreeCAD path")
        ),
    )
    assert parts_library.get_parts_list() == ["Part.FCStd"]
