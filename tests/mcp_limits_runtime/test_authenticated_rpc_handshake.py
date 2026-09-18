"""Runtime-info protocol reporting for authenticated vs unauthenticated RPC."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from freecad_mcp._shared.protocol.constants import SUPPORTED_FEATURES
from freecad_mcp._shared.protocol.runtime_manifest import RuntimeManifest
from freecad_mcp.build_info import protocol_version
from freecad_mcp.generated.capabilities.register_modules import tools_runtime_info
from freecad_mcp.server_state import ServerState
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

_UNAUTHENTICATED_V2_CAPABLE_INFO = {
    "ok": True,
    "instance_id": "profile-unauth",
    "profile_instance_id": "profile-unauth",
    "addon_runtime_id": "addon-runtime-unauth",
    "pid": 4242,
    "protocol_versions": [1, 2],
    "protocol_version": 1,
    "rpc_v2_session_ready": False,
    "protocol_features": [],
    "addon_version": "0.2.0",
    "addon_build_id": "freecad-mcp-0.2.0+unknown",
    "freecad_version": ["1", "2", "3"],
    "profile_path_fingerprint": "profile-fingerprint-unauth",
}


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


def test_unauthenticated_v2_capable_is_not_protocol_mismatch(monkeypatch) -> None:
    payload = _runtime_payload(
        monkeypatch,
        instance_info=_UNAUTHENTICATED_V2_CAPABLE_INFO,
    )

    warnings = payload["compatibility"]["warnings"]
    assert payload["compatibility"]["compatible"] is False
    assert payload["tool_availability"]["authenticated_rpc_v2"] is False
    assert not any("RPC protocol mismatch" in warning for warning in warnings)
    assert any("Authenticated runtime identity is not available" in warning for warning in warnings)
    assert payload["rpc"]["protocol_versions"] == [1, 2]
    assert payload["rpc"]["protocol_version"] == 1
    assert payload["rpc"]["rpc_v2_session_ready"] is False
    assert payload["rpc"]["authenticated_session"] is False


def test_authenticated_v2_matched_session_enables_gated_tools(monkeypatch) -> None:
    payload = _runtime_payload(monkeypatch, manifest=_authenticated_manifest())

    assert payload["compatibility"]["compatible"] is True
    assert payload["tool_availability"]["authenticated_rpc_v2"] is True
    assert payload["tool_availability"]["unavailable_tools"] == []
    assert payload["rpc"]["protocol_version"] == protocol_version
    assert payload["rpc"]["protocol_versions"] == [1, protocol_version]
    assert payload["rpc"]["rpc_v2_session_ready"] is True
    assert payload["rpc"]["authenticated_session"] is True
    assert set(payload["rpc"]["features"]) == set(SUPPORTED_FEATURES)


def test_true_v1_addon_reports_protocol_mismatch(monkeypatch) -> None:
    payload = _runtime_payload(
        monkeypatch,
        instance_info={
            **_UNAUTHENTICATED_V2_CAPABLE_INFO,
            "protocol_versions": [1],
            "protocol_version": 1,
            "rpc_v2_session_ready": False,
        },
    )

    warnings = payload["compatibility"]["warnings"]
    assert payload["compatibility"]["compatible"] is False
    assert payload["tool_availability"]["authenticated_rpc_v2"] is False
    assert any("RPC protocol mismatch" in warning for warning in warnings)
