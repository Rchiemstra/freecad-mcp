from __future__ import annotations

import importlib
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from freecad_mcp import build_info
from freecad_mcp.rpc_session import RpcAuthenticationSession

pytestmark = pytest.mark.unit


_ENVIRONMENT = (
    "FREECAD_MCP_BUILD_ID",
    "FREECAD_MCP_BUILD_TIMESTAMP",
    "FREECAD_MCP_GIT_COMMIT",
    "FREECAD_MCP_GIT_DIRTY",
)


def _clear(monkeypatch):
    for name in _ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


def test_build_info_deterministic_fallback_without_git(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.delitem(sys.modules, "freecad_mcp._build_metadata", raising=False)
    monkeypatch.setattr(build_info.metadata, "version", lambda _name: "9.8.7")
    reloaded = importlib.reload(build_info)
    assert reloaded.build_id == "freecad-mcp-9.8.7+unknown"
    assert reloaded.git_commit == "unknown"
    assert reloaded.git_dirty is None


def test_build_info_environment_overrides_generated_metadata(monkeypatch):
    _clear(monkeypatch)
    generated = ModuleType("freecad_mcp._build_metadata")
    generated.GIT_COMMIT = "generated"
    generated.GIT_DIRTY = False
    generated.BUILD_TIMESTAMP = "generated-time"
    generated.BUILD_ID = "generated-build"
    monkeypatch.setitem(sys.modules, "freecad_mcp._build_metadata", generated)
    monkeypatch.setenv("FREECAD_MCP_GIT_COMMIT", "environment")
    monkeypatch.setenv("FREECAD_MCP_GIT_DIRTY", "true")
    monkeypatch.setenv("FREECAD_MCP_BUILD_TIMESTAMP", "environment-time")
    monkeypatch.setenv("FREECAD_MCP_BUILD_ID", "environment-build")

    reloaded = importlib.reload(build_info)
    assert reloaded.git_commit == "environment"
    assert reloaded.git_dirty is True
    assert reloaded.build_timestamp == "environment-time"
    assert reloaded.build_id == "environment-build"


def _manifest(server_module, *, build_id: str, protocol_version: int = 2):
    return SimpleNamespace(
        addon_version=server_module.package_version,
        addon_build_id=build_id,
        addon_runtime_id="addon-runtime",
        protocol_version=protocol_version,
        features=tuple(server_module.REQUIRED_PROTOCOL_FEATURES),
        freecad_version="1.1.0",
        freecad_revision="revision",
        freecad_pid=456,
        profile_id="profile-id",
        profile_path_fingerprint="profile-fingerprint",
    )


def test_runtime_info_matching_identity_and_no_credentials(monkeypatch):
    from freecad_mcp import server

    manifest = _manifest(server, build_id=server.build_id)
    monkeypatch.setattr(server.state, "authenticated_manifest", manifest)
    monkeypatch.setattr(server.state, "mcp_instance_id", "mcp-runtime")
    monkeypatch.setattr(server.state, "mcp_pid", 123)
    # Runtime info is built exclusively from public manifest/build fields, even
    # if the short-lived authentication session contains a sentinel token.
    authentication = RpcAuthenticationSession()
    authentication.mark_connected("do-not-expose")
    monkeypatch.setattr(server.state, "rpc_session", authentication)
    response = server.get_runtime_info(None)
    payload = response.structuredContent["data"]
    assert payload["mcp"]["build_id"] == server.build_id
    assert payload["addon"]["runtime_id"] == "addon-runtime"
    assert payload["freecad"]["pid"] == 456
    assert payload["rpc"]["protocol_version"] == 2
    assert payload["compatibility"] == {"compatible": True, "warnings": []}
    assert payload["tool_availability"] == {
        "authenticated_rpc_v2": True,
        "unavailable_tools": [],
        "degraded_tools": [],
    }
    assert "do-not-expose" not in json.dumps(response.structuredContent)


def test_runtime_info_warns_for_compatible_build_mismatch(monkeypatch):
    from freecad_mcp import server

    monkeypatch.setattr(
        server.state,
        "authenticated_manifest",
        _manifest(server, build_id="other-compatible-build"),
    )
    compatibility = server._runtime_info_payload()["compatibility"]
    assert compatibility["compatible"] is True
    assert any("build IDs differ" in item for item in compatibility["warnings"])


def test_runtime_info_marks_protocol_mismatch_incompatible(monkeypatch):
    from freecad_mcp import server

    monkeypatch.setattr(
        server.state,
        "authenticated_manifest",
        _manifest(server, build_id=server.build_id, protocol_version=1),
    )
    payload = server._runtime_info_payload()
    compatibility = payload["compatibility"]
    assert compatibility["compatible"] is False
    assert any("protocol mismatch" in item for item in compatibility["warnings"])
    unavailable = {
        item["tool"] for item in payload["tool_availability"]["unavailable_tools"]
    }
    degraded = {item["tool"] for item in payload["tool_availability"]["degraded_tools"]}
    assert {"save_document", "refresh_view", "get_report_view"} <= unavailable
    assert {"save_document_as", "save_document_copy"} == degraded


@pytest.fixture(autouse=True)
def restore_build_info(monkeypatch):
    yield
    _clear(monkeypatch)
    monkeypatch.delitem(sys.modules, "freecad_mcp._build_metadata", raising=False)
    importlib.reload(build_info)
