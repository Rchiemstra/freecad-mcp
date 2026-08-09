"""Phase 18 plain-RPC session elevation and invoke_v2 error surfacing."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from addon.FreeCADMCP.rpc_server.json_rpc_errors import json_rpc_error_from_result
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_core import (
    dispatch as dispatch_core,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_core import (
    request_actor,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.freecad_client_ops.connection_methods.connection_headers_ops import (
    configure_rpc_session,
)
from freecad_mcp.rpc_session import RpcAuthenticationSession

pytestmark = pytest.mark.unit


def _connected_session(token: str = "rpc-session-secret") -> RpcAuthenticationSession:
    session = RpcAuthenticationSession()
    session.mark_connected(
        token,
        session_id="session-id",
        expires_at="2099-01-01T00:00:00Z",
    )
    return session


def _identity_provider(*, identity: dict | None = None):
    stored = dict(identity or {})

    def get_request_identity():
        return dict(stored)

    def set_request_identity(**values):
        stored.clear()
        stored.update(values)

    return SimpleNamespace(
        get_request_identity=get_request_identity,
        set_request_identity=set_request_identity,
        _stored=stored,
    )


def _execution_collaborators(
    *,
    identity: dict,
    session_id: str = "authenticated-session",
):
    provider = _identity_provider(identity=identity)
    session = SimpleNamespace(
        session_id=session_id,
        mcp=SimpleNamespace(process_started_at="process-start"),
    )

    def authenticate(token, *, mcp_runtime_id):
        assert token == identity.get("rpc_session_token")
        assert mcp_runtime_id == identity.get("instance_id")
        return session

    collaborators = SimpleNamespace(
        request_identity_provider=lambda: provider,
        session_manager=SimpleNamespace(authenticate=authenticate),
        lease_protocol_public_error=lambda exc, request_id=None: {
            "error": {"code": "LEASE_PROTOCOL_ERROR", "message": str(exc)},
            "request_id": request_id,
        },
    )
    return collaborators, provider


def test_plain_rpc_dispatch_elevates_session_for_gui_methods() -> None:
    identity = {
        "instance_id": "runtime-1",
        "rpc_session_token": "session-token",
        "request_id": "request-1",
    }
    collaborators, provider = _execution_collaborators(identity=identity)
    calls = []

    def get_gui_state():
        calls.append("called")
        return {"ok": True}

    facade = SimpleNamespace(
        _execution_collaborators=collaborators,
        get_gui_state=get_gui_state,
        _gui_collaborators=SimpleNamespace(
            get_request_identity=provider.get_request_identity,
        ),
    )

    assert dispatch_core(facade, "get_gui_state", ()) == {"ok": True}
    assert calls == ["called"]
    assert provider._stored["authenticated_session_id"] == "authenticated-session"
    assert request_actor(facade) == "runtime-1"


def test_plain_rpc_dispatch_without_token_fails_closed() -> None:
    identity = {"instance_id": "runtime-1", "request_id": "request-1"}
    collaborators, _provider = _execution_collaborators(identity=identity)
    facade = SimpleNamespace(
        _execution_collaborators=collaborators,
        get_gui_state=lambda: pytest.fail("must not call handler"),
    )

    result = dispatch_core(facade, "get_gui_state", ())

    assert result == {
        "success": False,
        "error_code": "LEASE_PROTOCOL_REQUIRED",
        "error": (
            "This operation requires a handshake_v2 session and an "
            "immutable authenticated request envelope"
        ),
    }


def test_plain_rpc_dispatch_skips_reauth_when_already_elevated() -> None:
    identity = {
        "instance_id": "runtime-1",
        "rpc_session_token": "session-token",
        "authenticated_session_id": "already-elevated",
        "request_id": "request-1",
    }
    collaborators, provider = _execution_collaborators(identity=identity)
    collaborators.session_manager.authenticate = MagicMock(
        side_effect=AssertionError("must not re-authenticate")
    )
    facade = SimpleNamespace(
        _execution_collaborators=collaborators,
        get_selection=lambda: {"selection": []},
        _gui_collaborators=SimpleNamespace(
            get_request_identity=provider.get_request_identity,
        ),
    )

    assert dispatch_core(facade, "get_selection", ()) == {"selection": []}


def test_invoke_v2_failure_unwraps_nested_result_error() -> None:
    result = {
        "ok": False,
        "request_id": "request-2",
        "addon_runtime_id": "runtime-2",
        "result": {
            "success": False,
            "error_code": "gui_timeout_not_supported",
            "error": "timeout_seconds is a hard worker timeout",
        },
    }

    error = json_rpc_error_from_result(result)

    assert error == {
        "code": -32000,
        "message": "timeout_seconds is a hard worker timeout",
        "data": {
            "request_id": "request-2",
            "addon_runtime_id": "runtime-2",
            "error_code": "gui_timeout_not_supported",
        },
    }


def test_invoke_v2_failure_unwraps_document_health_degraded() -> None:
    result = {
        "ok": False,
        "request_id": "request-3",
        "result": {
            "success": False,
            "error_code": "DOCUMENT_HEALTH_DEGRADED",
            "error": "document health check failed",
            "details": {"verdict": "degraded"},
        },
    }

    error = json_rpc_error_from_result(result)

    assert error["message"] == "document health check failed"
    assert error["data"]["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
    assert error["data"]["verdict"] == "degraded"


def test_get_gui_state_routes_through_invoke_v2_when_session_connected(
    monkeypatch,
) -> None:
    conn = FreeCADConnection()
    configure_rpc_session(conn, _connected_session())
    captured = {}

    def invoke_v2(method, params, context, *, control=False, timeout=None):
        del control, timeout
        captured["method"] = method
        captured["params"] = dict(params)
        captured["envelope"] = context.to_envelope(method, params)
        return {"ok": True, "result": {"success": True, "active_document": "Demo"}}

    monkeypatch.setattr(conn, "invoke_v2", invoke_v2)

    result = conn.get_gui_state()

    assert result == {"success": True, "active_document": "Demo"}
    assert captured["method"] == "get_gui_state"
    assert captured["envelope"]["session_token"] == "rpc-session-secret"
    assert captured["envelope"]["lease_credentials"] == []
    conn.disconnect()


def test_get_selection_routes_through_invoke_v2_when_session_connected(
    monkeypatch,
) -> None:
    conn = FreeCADConnection()
    configure_rpc_session(conn, _connected_session())
    captured = {}

    def invoke_v2(method, params, context, *, control=False, timeout=None):
        del control, timeout
        captured["method"] = method
        captured["envelope"] = context.to_envelope(method, params)
        return {
            "ok": True,
            "result": {"success": True, "selection": [], "count": 0},
        }

    monkeypatch.setattr(conn, "invoke_v2", invoke_v2)

    result = conn.get_selection()

    assert result == {"success": True, "selection": [], "count": 0}
    assert captured["method"] == "get_selection"
    assert captured["envelope"]["request_id"]
    conn.disconnect()


def test_gui_context_runtime_reports_missing_personal_view_api() -> None:
    from addon.FreeCADMCP.rpc_server import gui_context_runtime

    gui = SimpleNamespace()

    with pytest.raises(
        gui_context_runtime.PersonalViewApiUnavailableError
    ) as raised:
        gui_context_runtime.snapshot(gui, "Model", "runtime")

    assert raised.value.code == "PERSONAL_VIEW_API_UNAVAILABLE"
    assert "FreeCADGui.getPersonalViewContext" in str(raised.value)


def test_get_gui_state_surfaces_personal_view_api_unavailable() -> None:
    from functools import partial

    from addon.FreeCADMCP.rpc_server import gui_context_runtime
    from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.gui_interaction import (
        get_gui_state,
    )

    gui = SimpleNamespace()
    document = SimpleNamespace(Name="Model", Label="Model")
    registry = SimpleNamespace(
        remember=lambda *_args, **_kwargs: None,
        activate=lambda *_args, **_kwargs: None,
        current_target=lambda *_args: None,
        metadata=lambda *_args: {},
    )
    facade = SimpleNamespace(
        _gui_collaborators=SimpleNamespace(
            get_request_identity=lambda: {
                "authenticated_session_id": "session",
                "instance_id": "runtime",
            },
            freecad=SimpleNamespace(listDocuments=lambda: {"Model": document}),
            dispatch_gui=lambda _facade, callback, **_kwargs: callback(),
            snapshot_view_context=lambda _name: None,
            snapshot_personal_view_context=partial(
                gui_context_runtime.snapshot, gui
            ),
            store_personal_view_context=partial(gui_context_runtime.store, gui),
            personal_view_registry=registry,
            reraise_if_cancelled=lambda _error: None,
            redact_rpc_diagnostic=lambda error: str(error),
        ),
    )

    result = get_gui_state(facade)

    assert result == {
        "ok": False,
        "success": False,
        "error_code": "PERSONAL_VIEW_API_UNAVAILABLE",
        "error": (
            "FreeCAD must expose FreeCADGui.getPersonalViewContext "
            "(rebuild/redeploy past collaboration personal-view support)"
        ),
    }
