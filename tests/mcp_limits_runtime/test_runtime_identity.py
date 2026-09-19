"""Runtime identity: compiled vs checkout, unknown honesty, path rejection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from freecad_mcp._shared.protocol.runtime_manifest import RuntimeManifest
from freecad_mcp.generated.capabilities.register_modules import tools_runtime_info
from freecad_mcp.server_ops import runtime_identity
from freecad_mcp.server_state import ServerState
from scripts.generate_build_metadata import build_metadata
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit


def _runtime_payload(
    monkeypatch,
    *,
    manifest: RuntimeManifest | None = None,
    instance_info: dict | None = None,
) -> dict:
    bootstrap_unit_test_runtime()
    state = ServerState()
    state.authenticated_manifest = manifest
    connection = MagicMock(name="FreeCADConnection")
    if instance_info is not None:
        connection.get_instance_info.return_value = instance_info
    monkeypatch.setattr(tools_runtime_info, "server_state", lambda: state)
    monkeypatch.setattr(tools_runtime_info, "server_connection", lambda: connection)
    return tools_runtime_info._runtime_info_payload()


def _authenticated_manifest() -> RuntimeManifest:
    return RuntimeManifest(
        profile_id="profile-auth",
        addon_runtime_id="8c897b64-0f04-4e09-9f80-2873d4527b7f",
        freecad_pid=4321,
        freecad_process_started_at="2026-07-22T10:00:00Z",
        boot_id="boot-auth",
        rpc_host="127.0.0.1",
        rpc_port=9876,
        freecad_version="1.0.0",
        freecad_revision="abc123",
        addon_version="0.1.20",
        addon_build_id="build-auth",
        profile_path_fingerprint="sha256:0123456789abcdef",
    )


def test_mcp_payload_splits_compiled_and_checkout(monkeypatch) -> None:
    payload = _runtime_payload(
        monkeypatch,
        instance_info={
            "ok": True,
            "protocol_versions": [1, 2],
            "addon_build_id": "freecad-mcp-0.2.0+unknown",
        },
    )

    assert "compiled" in payload["mcp"]
    assert "checkout" in payload["mcp"]
    assert "source" in payload["mcp"]["compiled"]
    assert "available" in payload["mcp"]["checkout"]


def test_compatibility_identity_block(monkeypatch) -> None:
    payload = _runtime_payload(
        monkeypatch,
        instance_info={"ok": True, "protocol_versions": [1, 2]},
    )

    identity = payload["compatibility"]["identity"]
    assert set(identity) == {
        "mcp_addon",
        "compiled_checkout",
        "unknown_unmatched",
        "checkout_match",
    }


def test_unknown_unknown_is_not_a_match(monkeypatch) -> None:
    payload = _runtime_payload(
        monkeypatch,
        instance_info={
            "ok": True,
            "protocol_versions": [1, 2],
            "addon_build_id": "freecad-mcp-0.2.0+unknown",
            "git_commit": "unknown",
        },
    )

    identity = payload["compatibility"]["identity"]
    warnings = payload["compatibility"]["warnings"]
    assert identity["unknown_unmatched"] is True
    assert identity["mcp_addon"] is False
    assert any(
        "identities are both unknown" in warning.lower() for warning in warnings
    )


def test_matching_compiled_builds_do_not_warn(monkeypatch) -> None:
    build_id = "freecad-mcp-0.2.0+deadbeef1234"
    commit = "deadbeef1234567890deadbeef1234567890deadbeef"
    monkeypatch.setattr(
        tools_runtime_info,
        "mcp_build_info",
        lambda: {
            "compiled": {
                "version": "0.2.0",
                "build_id": build_id,
                "git_commit": commit,
                "git_dirty": False,
                "build_timestamp": "2026-01-01T00:00:00Z",
                "source": "generated_metadata",
            },
            "checkout": {
                "git_commit": commit,
                "git_dirty": False,
                "available": True,
            },
        },
    )
    payload = _runtime_payload(
        monkeypatch,
        instance_info={
            "ok": True,
            "protocol_versions": [1, 2],
            "addon_build_id": build_id,
            "git_commit": commit,
            "git_dirty": False,
        },
    )

    identity = payload["compatibility"]["identity"]
    assert identity["mcp_addon"] is True
    assert identity["unknown_unmatched"] is False
    assert not any("build IDs differ" in warning for warning in payload["compatibility"]["warnings"])


def test_stale_compiled_checkout_warns(monkeypatch) -> None:
    compiled_commit = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    checkout_commit = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    monkeypatch.setattr(
        tools_runtime_info,
        "mcp_build_info",
        lambda: {
            "compiled": {
                "version": "0.2.0",
                "build_id": "freecad-mcp-0.2.0+aaaaaaaaaaaa",
                "git_commit": compiled_commit,
                "git_dirty": False,
                "build_timestamp": "2026-01-01T00:00:00Z",
                "source": "generated_metadata",
            },
            "checkout": {
                "git_commit": checkout_commit,
                "git_dirty": True,
                "available": True,
            },
        },
    )
    payload = _runtime_payload(
        monkeypatch,
        instance_info={
            "ok": True,
            "protocol_versions": [1, 2],
            "addon_build_id": "freecad-mcp-0.2.0+aaaaaaaaaaaa",
            "git_commit": compiled_commit,
        },
    )

    identity = payload["compatibility"]["identity"]
    assert identity["compiled_checkout"] is False
    assert any("Checkout commit differs" in warning for warning in payload["compatibility"]["warnings"])


def test_path_shaped_git_commit_rejected() -> None:
    unix_path = "/home/msi/FreeCAD/build/release/bin/FreeCAD"
    assert runtime_identity.sanitize_git_commit("/proc/123/exe") == "unknown"
    assert runtime_identity.sanitize_git_commit("C:\\Program Files\\FreeCAD.exe") == "unknown"
    assert runtime_identity.sanitize_git_commit("D:/build/FreeCAD.exe") == "unknown"
    assert runtime_identity.sanitize_git_commit(unix_path) == "unknown"
    assert (
        runtime_identity.sanitize_git_commit("deadbeef1234567890deadbeef1234567890deadbeef")
        == "deadbeef1234567890deadbeef1234567890deadbeef"
    )

    from addon.FreeCADMCP import build_info as addon_build_info

    assert addon_build_info._sanitize_git_commit(unix_path) == "unknown"


def test_find_git_root_walks_up_from_nested_package(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    module = repo / "src" / "pkg" / "mod.py"
    module.parent.mkdir(parents=True)
    module.write_text("# stub\n", encoding="utf-8")
    (repo / ".git").mkdir()

    assert runtime_identity._find_git_root(module) == repo
    assert runtime_identity._find_git_root(module) != repo / "src"


def test_find_git_root_returns_none_without_git_metadata(tmp_path: Path) -> None:
    module = tmp_path / "src" / "pkg" / "mod.py"
    module.parent.mkdir(parents=True)
    module.write_text("# stub\n", encoding="utf-8")

    assert runtime_identity._find_git_root(module) is None


def test_find_git_root_accepts_git_file_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    module = repo / "src" / "pkg" / "mod.py"
    module.parent.mkdir(parents=True)
    module.write_text("# stub\n", encoding="utf-8")
    (repo / ".git").write_text("gitdir: /path/to/worktree.git\n", encoding="utf-8")

    assert runtime_identity._find_git_root(module) == repo


def test_read_checkout_git_honest_without_git_metadata() -> None:
    git_root = runtime_identity._git_root()
    checkout = runtime_identity.read_checkout_git()

    if git_root is None:
        assert checkout == {
            "git_commit": "unknown",
            "git_dirty": None,
            "available": False,
        }
        return

    src_root = Path(runtime_identity.__file__).resolve().parents[2]
    assert git_root != src_root or not (src_root / ".git").exists()
    assert checkout["available"] is True
    assert checkout["git_commit"] != "unknown"


def test_stale_mcp_vs_addon_commits_warn_with_unknown_build_ids() -> None:
    mcp_commit = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    addon_commit = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    result = runtime_identity.identity_compatibility(
        mcp_compiled={
            "build_id": "freecad-mcp-0.2.0+unknown",
            "git_commit": mcp_commit,
        },
        addon_compiled={
            "build_id": "freecad-mcp-0.2.0+unknown",
            "git_commit": addon_commit,
        },
        mcp_checkout={"available": False},
    )

    assert result["unknown_unmatched"] is False
    assert result["mcp_addon"] is False
    assert any("git commits differ" in warning.lower() for warning in result["warnings"])


def test_stale_mcp_vs_addon_build_ids_warn() -> None:
    commit = "deadbeef1234567890deadbeef1234567890deadbeef"
    result = runtime_identity.identity_compatibility(
        mcp_compiled={
            "build_id": "freecad-mcp-0.2.0+deadbeef1234",
            "git_commit": commit,
        },
        addon_compiled={
            "build_id": "freecad-mcp-0.2.0+cafebabe5678",
            "git_commit": commit,
        },
        mcp_checkout={"available": False},
    )

    assert result["unknown_unmatched"] is False
    assert result["mcp_addon"] is False
    assert any("build IDs differ" in warning for warning in result["warnings"])


def test_dirty_checkout_visible_without_mutating_compiled_dirty(monkeypatch) -> None:
    commit = "deadbeef1234567890deadbeef1234567890deadbeef"
    monkeypatch.setattr(
        tools_runtime_info,
        "mcp_build_info",
        lambda: {
            "compiled": {
                "version": "0.2.0",
                "build_id": "freecad-mcp-0.2.0+deadbeef1234",
                "git_commit": commit,
                "git_dirty": False,
                "build_timestamp": "2026-01-01T00:00:00Z",
                "source": "generated_metadata",
            },
            "checkout": {
                "git_commit": commit,
                "git_dirty": True,
                "available": True,
            },
        },
    )
    payload = _runtime_payload(
        monkeypatch,
        instance_info={
            "ok": True,
            "protocol_versions": [1, 2],
            "addon_build_id": "freecad-mcp-0.2.0+deadbeef1234",
            "git_commit": commit,
        },
    )

    assert payload["mcp"]["compiled"]["git_dirty"] is False
    assert payload["mcp"]["checkout"]["git_dirty"] is True
    assert payload["mcp"]["checkout"]["available"] is True


def test_generate_build_metadata_unknown_git_dirty_is_null() -> None:
    metadata = build_metadata(version="0.2.0", git_commit="unknown")
    assert metadata["git_commit"] == "unknown"
    assert metadata["git_dirty"] is None


def test_environment_overlay_source(monkeypatch) -> None:
    monkeypatch.setenv("FREECAD_MCP_GIT_COMMIT", "cafebabecafebabecafebabecafebabecafebabe")
    monkeypatch.delenv("FREECAD_MCP_BUILD_ID", raising=False)
    monkeypatch.delenv("FREECAD_MCP_BUILD_TIMESTAMP", raising=False)
    monkeypatch.delenv("FREECAD_MCP_GIT_DIRTY", raising=False)

    from freecad_mcp import build_info

    compiled = build_info.compiled_identity()
    assert compiled["source"] == "environment"
    assert compiled["git_commit"] == "cafebabecafebabecafebabecafebabecafebabe"


def test_authenticated_still_merges_instance_info_extras(monkeypatch) -> None:
    manifest = _authenticated_manifest()
    connection = MagicMock(name="FreeCADConnection")
    connection.get_instance_info.return_value = {
        "git_commit": "feedfacefeedfacefeedfacefeedfacefeedface",
        "git_dirty": True,
        "build_timestamp": "2026-02-02T12:00:00Z",
        "addon_metadata_source": "generated_metadata",
        "freecad_git_commit": "0123456789abcdef0123456789abcdef01234567",
    }
    bootstrap_unit_test_runtime()
    state = ServerState()
    state.authenticated_manifest = manifest
    monkeypatch.setattr(tools_runtime_info, "server_state", lambda: state)
    monkeypatch.setattr(tools_runtime_info, "server_connection", lambda: connection)

    payload = tools_runtime_info._runtime_info_payload()

    connection.get_instance_info.assert_called_once()
    assert payload["addon"]["compiled"]["git_commit"] == (
        "feedfacefeedfacefeedfacefeedfacefeedface"
    )
    assert payload["addon"]["compiled"]["git_dirty"] is True
    assert payload["freecad"]["compiled"]["git_commit"] == (
        "0123456789abcdef0123456789abcdef01234567"
    )


def test_freecad_compiled_exposes_build_revision_hash(monkeypatch) -> None:
    revision_hash = "0123456789abcdef0123456789abcdef01234567"
    payload = _runtime_payload(
        monkeypatch,
        instance_info={
            "ok": True,
            "protocol_versions": [1, 2],
            "freecad_git_commit": revision_hash,
            "freecad_version": ["1", "0", "0", "12345"],
        },
    )

    assert payload["freecad"]["compiled"]["git_commit"] == revision_hash
    assert payload["freecad"]["compiled"]["version"] == "1.0.0"
    assert payload["freecad"]["compiled"]["revision"] == "12345"


def test_build_info_as_dict_is_per_request(monkeypatch) -> None:
    from freecad_mcp import build_info

    calls = {"count": 0}

    def fake_compiled() -> dict:
        calls["count"] += 1
        suffix = "aaaa" if calls["count"] == 1 else "bbbb"
        return {
            "version": "0.2.0",
            "build_id": f"freecad-mcp-0.2.0+{suffix}",
            "git_commit": f"{suffix}{suffix}{suffix}{suffix}{suffix}{suffix}{suffix}{suffix}",
            "git_dirty": False,
            "build_timestamp": "2026-01-01T00:00:00Z",
            "source": "generated_metadata",
        }

    monkeypatch.setattr(build_info, "compiled_identity", fake_compiled)
    first = build_info.as_dict()
    second = build_info.as_dict()
    assert first["compiled"]["git_commit"] != second["compiled"]["git_commit"]


def test_addon_build_info_as_dict_is_per_request(monkeypatch) -> None:
    from addon.FreeCADMCP import build_info as addon_build_info

    calls = {"count": 0}

    def fake_compiled() -> dict:
        calls["count"] += 1
        suffix = "cccc" if calls["count"] == 1 else "dddd"
        return {
            "version": "0.2.0",
            "build_id": f"freecad-mcp-0.2.0+{suffix}",
            "git_commit": f"{suffix}{suffix}{suffix}{suffix}{suffix}{suffix}{suffix}{suffix}",
            "git_dirty": None,
            "build_timestamp": "2026-01-01T00:00:00Z",
            "source": "generated_metadata",
        }

    monkeypatch.setattr(addon_build_info, "compiled_identity", fake_compiled)
    first = addon_build_info.as_dict()
    second = addon_build_info.as_dict()
    assert first["compiled"]["git_commit"] != second["compiled"]["git_commit"]


def test_addon_get_instance_info_exposes_build_metadata(monkeypatch) -> None:
    """get_instance_info returns git/build fields sourced from addon as_dict()."""
    from addon.FreeCADMCP.rpc_server.methods.lifecycle_methods_ops import (
        control_status,
    )

    build = {
        "compiled": {
            "git_commit": "abcabcabcabcabcabcabcabcabcabcabcabc",
            "git_dirty": True,
            "build_timestamp": "2026-03-03T00:00:00Z",
            "source": "generated_metadata",
        }
    }
    monkeypatch.setattr(control_status, "addon_build_info", lambda: build)
    monkeypatch.setattr(control_status, "addon_version", "0.2.0")
    monkeypatch.setattr(control_status, "addon_build_id", "freecad-mcp-0.2.0+abcabcabcabc")

    collaborators = MagicMock()
    collaborators.load_settings.return_value = {}
    collaborators.freecad.getUserAppDataDir.return_value = "/tmp/profile"
    collaborators.freecad_version_parts.return_value = ["1", "0", "0"]
    collaborators.freecad.ConfigGet.return_value = (
        "0123456789abcdef0123456789abcdef01234567"
    )
    collaborators.runtime_id = "runtime-test"
    collaborators.actual_endpoint = {"host": "127.0.0.1", "port": 9875}
    collaborators.runtime_manifest = None
    collaborators.process_started_at = "2026-01-01T00:00:00Z"
    collaborators.boot_id = "boot-test"
    collaborators.addon_loaded_at = "2026-01-01T00:00:01Z"
    collaborators.server_started_at = "2026-01-01T00:00:02Z"
    collaborators.session_manager = None
    collaborators.profile_fingerprint = "fp-test"

    rpc = MagicMock()
    rpc._execution_collaborators = collaborators
    info = control_status.get_instance_info(rpc)

    assert info["git_commit"] == build["compiled"]["git_commit"]
    assert info["git_dirty"] is True
    assert info["build_timestamp"] == build["compiled"]["build_timestamp"]
    assert info["addon_metadata_source"] == "generated_metadata"
    assert info["freecad_git_commit"] == "0123456789abcdef0123456789abcdef01234567"
    collaborators.freecad.ConfigGet.assert_called_with("BuildRevisionHash")
