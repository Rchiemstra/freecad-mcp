"""Regression: open_document auth, v2 runtime binding, and fail-closed client."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from addon.FreeCADMCP.rpc_server.json_rpc_errors import json_rpc_error_from_result
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_core import (
    dispatch as dispatch_core,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops import document_ops
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


def test_open_document_calls_request_actor_before_gui_dispatch(monkeypatch) -> None:
    order: list[str] = []

    monkeypatch.setattr(
        document_ops,
        "request_actor",
        lambda facade: order.append("actor") or "runtime",
    )
    monkeypatch.setattr(
        document_ops,
        "dispatch_gui",
        lambda facade, callback, **_kwargs: order.append("dispatch") or callback(),
    )
    monkeypatch.setattr(
        document_ops,
        "_open_checked",
        lambda facade, path, actor: {
            "ok": True,
            "document": "Model",
            "actor": actor,
        },
    )

    facade = SimpleNamespace(_gui_collaborators=MagicMock())
    result = document_ops.open_document(facade, "/model.FCStd")

    assert order == ["actor", "dispatch"]
    assert result == {"ok": True, "document": "Model", "actor": "runtime"}


def test_open_document_handler_without_identity_returns_lease_protocol_required() -> None:
    facade = SimpleNamespace(
        _gui_collaborators=SimpleNamespace(
            get_request_identity=lambda: {},
            reraise_if_cancelled=lambda _error: None,
            redact_rpc_diagnostic=lambda error: str(error),
        )
    )

    result = document_ops.open_document(facade, "/model.FCStd")

    assert result.get("ok") is False or result.get("success") is False
    assert result["error_code"] == "LEASE_PROTOCOL_REQUIRED"
    error = json_rpc_error_from_result(result)
    assert error is not None
    assert error["data"]["error_code"] == "LEASE_PROTOCOL_REQUIRED"


def test_dispatch_core_open_document_without_token_does_not_call_handler() -> None:
    identity = {"instance_id": "runtime-1", "request_id": "request-1"}
    collaborators, _provider = _execution_collaborators(identity=identity)
    facade = SimpleNamespace(
        _execution_collaborators=collaborators,
        open_document=lambda _path: pytest.fail("must not call handler"),
    )

    result = dispatch_core(facade, "open_document", ("/model.FCStd",))

    assert result == {
        "success": False,
        "error_code": "LEASE_PROTOCOL_REQUIRED",
        "error": (
            "This operation requires a handshake_v2 session and an "
            "immutable authenticated request envelope"
        ),
    }


def test_dispatch_core_open_document_with_session_elevates_and_calls_handler() -> None:
    identity = {
        "instance_id": "runtime-1",
        "rpc_session_token": "session-token",
        "request_id": "request-1",
    }
    collaborators, provider = _execution_collaborators(identity=identity)
    expected = {"ok": True, "document": "Model"}
    facade = SimpleNamespace(
        _execution_collaborators=collaborators,
        open_document=lambda _path: expected,
        _gui_collaborators=SimpleNamespace(
            get_request_identity=provider.get_request_identity,
        ),
    )

    result = dispatch_core(facade, "open_document", ("/model.FCStd",))

    assert result == expected
    assert provider._stored["authenticated_session_id"] == "authenticated-session"
    assert request_actor(facade) == "runtime-1"


def test_open_document_invoke_v2_envelope_binds_runtime_id(monkeypatch) -> None:
    conn = FreeCADConnection()
    configure_rpc_session(conn, _connected_session())
    runtime_id = str(uuid.uuid4())
    conn._mcp_instance_id = runtime_id
    captured: dict[str, object] = {}

    def invoke_v2(method, params, context, *, control=False, timeout=None):
        del control, timeout
        captured["method"] = method
        captured["envelope"] = context.to_envelope(method, params)
        return {"ok": True, "result": {"ok": True, "document": "Demo"}}

    monkeypatch.setattr(conn, "invoke_v2", invoke_v2)

    result = conn.open_document("C:/tmp/demo.FCStd")

    assert result == {"ok": True, "document": "Demo"}
    assert captured["method"] == "open_document"
    envelope = captured["envelope"]
    assert isinstance(envelope, dict)
    assert envelope["mcp_runtime_id"] == runtime_id

    class _RuntimeBindingManager:
        def authenticate(self, _token, *, mcp_runtime_id):
            assert mcp_runtime_id == runtime_id
            return SimpleNamespace(
                session_id="session-id",
                mcp=SimpleNamespace(process_started_at="process-start"),
            )

        def authenticate_envelope(self, payload, *, transport_mcp_runtime_id=None):
            assert transport_mcp_runtime_id is None
            assert payload["mcp_runtime_id"] == runtime_id
            return self.authenticate(
                payload["session_token"], mcp_runtime_id=runtime_id
            ), envelope

    _RuntimeBindingManager().authenticate_envelope(
        envelope, transport_mcp_runtime_id=None
    )
    conn.disconnect()


def test_open_document_without_session_does_not_call_plain_rpc(monkeypatch) -> None:
    conn = FreeCADConnection()
    assert conn._rpc_session is None

    def forbidden_open(_path):
        pytest.fail("plain RPC open_document must not be called without v2 session")

    monkeypatch.setattr(conn.server, "open_document", forbidden_open)

    result = conn.open_document("/model.FCStd")

    assert result.get("success") is False
    assert result["error_code"] == "LEASE_PROTOCOL_REQUIRED"
