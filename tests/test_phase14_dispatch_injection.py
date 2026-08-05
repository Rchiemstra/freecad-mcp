"""Phase 18 contracts for native dispatch and authentication-only control."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.lifecycle_methods_ops.control_status import (
    get_instance_info,
)
from addon.FreeCADMCP.rpc_server.methods.v2_methods_ops.handshake import handshake_v2
from addon.FreeCADMCP.rpc_server.methods.v2_methods_ops.invoke_v2_control import (
    invoke_v2_control,
)
from addon.FreeCADMCP.rpc_server.methods.v2_methods_ops.invoke_v2_dispatch import (
    register_invoke_v2_inflight,
    set_invoke_v2_request_identity,
)

pytestmark = pytest.mark.unit


ROOT = Path(__file__).parents[1]
LIVE_PRODUCTION = (
    ROOT / "addon/FreeCADMCP/rpc_server/methods/dispatch_helpers_ops/dispatch_core.py",
    ROOT / "addon/FreeCADMCP/rpc_server/methods/v2_methods_ops/invoke_v2.py",
    ROOT / "addon/FreeCADMCP/rpc_server/methods/v2_methods_ops/invoke_v2_dispatch.py",
    ROOT / "addon/FreeCADMCP/rpc_server/methods/v2_methods_ops/invoke_v2_finalize.py",
    ROOT
    / "addon/FreeCADMCP/rpc_server/methods/lifecycle_methods_ops/control_cancel.py",
    ROOT
    / "addon/FreeCADMCP/rpc_server/methods/lifecycle_methods_ops/control_cancel_finalize.py",
    ROOT
    / "addon/FreeCADMCP/rpc_server/methods/lifecycle_methods_ops/control_status.py",
)


def test_live_dispatch_slice_has_no_document_authority_imports() -> None:
    forbidden_modules = {
        "core_authority",
        "document_lease",
        "document_lock",
        "sidecar",
        "save_service",
    }
    for path in LIVE_PRODUCTION:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = {
            part
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for part in (node.module or "").split(".")
        } | {
            part
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            for part in alias.name.split(".")
        }
        assert forbidden_modules.isdisjoint(imported), path

    finalize_tree = ast.parse(
        LIVE_PRODUCTION[3].read_text(encoding="utf-8"),
        filename=str(LIVE_PRODUCTION[3]),
    )
    assert not any(isinstance(node, ast.Import) for node in ast.walk(finalize_tree))


def test_handshake_uses_only_the_injected_session_and_public_error() -> None:
    payload = object()
    expected = object()
    calls: list[tuple[str, object]] = []
    collaborators = SimpleNamespace(
        session_manager=SimpleNamespace(
            perform_handshake=lambda value: calls.append(("handshake", value))
            or expected
        ),
        lease_protocol_public_error=lambda exc: calls.append(("error", exc)),
    )
    facade = SimpleNamespace(_execution_collaborators=collaborators)

    assert handshake_v2(facade, payload) is expected
    assert calls == [("handshake", payload)]


def test_authenticated_identity_contains_no_document_credential() -> None:
    captured = {}
    identity_api = SimpleNamespace(
        set_request_identity=lambda **values: captured.update(values)
    )
    session = SimpleNamespace(
        session_id="session-1",
        mcp=SimpleNamespace(
            runtime_id="runtime-1",
            client_build_id="client-1",
            pid=42,
            hostname="host-1",
            process_started_at="process-1",
        ),
    )
    envelope = SimpleNamespace(
        request_id="request-1",
        session_token="session-token",
        operation=SimpleNamespace(task_id="task-1"),
    )

    set_invoke_v2_request_identity(
        identity_provider=identity_api,
        session=session,
        envelope=envelope,
        transport_identity={"rpc_port": 9875},
    )

    assert captured["authenticated_session_id"] == "session-1"
    assert captured["rpc_session_token"] == "session-token"
    assert not {"lease_token", "lease_id", "lease_generation"} & set(captured)


def test_inflight_registration_carries_no_document_credentials() -> None:
    calls = []
    registry = SimpleNamespace(
        register=lambda *args, **kwargs: calls.append((args, kwargs)) or object()
    )
    collaborators = SimpleNamespace(inflight_request_registry=registry)
    facade = SimpleNamespace(_ordered_envelope_params=lambda _target, params: params)
    session = SimpleNamespace(
        session_id="session-1", mcp=SimpleNamespace(runtime_id="mcp")
    )
    envelope = SimpleNamespace(
        request_id="request-1", method="get_gui_state", params={"x": 1}
    )

    params, _inflight = register_invoke_v2_inflight(
        collaborators=collaborators,
        self=facade,
        session=session,
        envelope=envelope,
        target=object(),
        replay_cache=SimpleNamespace(abandon=lambda *_args: None),
    )

    assert params == {"x": 1}
    assert calls == [
        (
            ("session-1", "request-1", "get_gui_state"),
            {},
        )
    ]


def test_control_lane_rejection_uses_the_injected_public_error() -> None:
    calls = []

    def public_error(exc, *, request_id=None):
        calls.append((exc, request_id))
        return {"mapped": True}

    facade = SimpleNamespace(
        _execution_collaborators=SimpleNamespace(
            lease_protocol_public_error=public_error
        )
    )

    assert invoke_v2_control(
        facade, {"method": "shutdown_rpc_server", "request_id": "request-1"}
    ) == {"mapped": True}
    assert len(calls) == 1
    assert calls[0][0].code == "METHOD_NOT_CONTROL"
    assert calls[0][1] == "request-1"


def test_instance_info_uses_eager_injected_status_values() -> None:
    collaborators = SimpleNamespace(
        load_settings=lambda: {"profile_instance_id": "profile-1"},
        freecad=SimpleNamespace(getUserAppDataDir=lambda: "/profile/"),
        freecad_version_parts=lambda: ("1", "2", "3"),
        actual_endpoint={"host": "127.0.0.1", "port": 9000},
        runtime_id="runtime-1",
        runtime_manifest=None,
        process_started_at="process-start",
        boot_id="boot-1",
        addon_loaded_at="addon-start",
        server_started_at="rpc-start",
        session_manager=object(),
        profile_fingerprint="profile-fingerprint",
    )

    result = get_instance_info(SimpleNamespace(_execution_collaborators=collaborators))

    assert result["freecad_process_started_at"] == "process-start"
    assert result["boot_id"] == "boot-1"
    assert result["profile_path_fingerprint"] == "profile-fingerprint"
    assert result["actual_endpoint"] is collaborators.actual_endpoint
    assert result["document_lease_mode"] == "off"
