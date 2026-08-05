from __future__ import annotations

import ast
import uuid
from pathlib import Path
from types import SimpleNamespace

from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.freecad_client_ops.connection_methods import connection_invoke_v2_ops
from freecad_mcp.freecad_client_ops.connection_methods.connection_headers_ops import (
    configure_rpc_session,
)
from freecad_mcp.rpc_session import (
    RpcAuthenticationContext,
    RpcAuthenticationSession,
)
from freecad_mcp.server_state import ServerState

REMOVED_STATE_FIELDS = frozenset(
    {
        "lease_manager",
        "document_sessions",
        "lease_tokens",
        "legacy_document_keys",
        "recovery_incidents",
    }
)


def _connected_session(token: str = "rpc-session-secret") -> RpcAuthenticationSession:
    session = RpcAuthenticationSession()
    session.mark_connected(
        token,
        session_id="session-id",
        expires_at="2099-01-01T00:00:00Z",
    )
    return session


def test_authentication_context_always_emits_empty_document_credentials() -> None:
    context = RpcAuthenticationContext(
        request_id=str(uuid.uuid4()),
        session_token="rpc-session-secret",
        operation_name="Edit object",
    )

    envelope = context.to_envelope("edit_object", {"doc_name": "Demo"})

    assert envelope["lease_credentials"] == []
    assert envelope["session_token"] == "rpc-session-secret"
    assert not hasattr(context, "lease_credentials")


def test_server_state_owns_only_rpc_authentication_session() -> None:
    state = ServerState()

    assert isinstance(state.rpc_session, RpcAuthenticationSession)
    assert REMOVED_STATE_FIELDS.isdisjoint(vars(state))


def test_connection_ignores_document_scope_when_building_v2_context() -> None:
    conn = FreeCADConnection()
    session = _connected_session()
    configure_rpc_session(conn, session)

    context = conn._build_v2_context(
        document_names=("Demo",),
        selectors=(
            {
                "document_name": "Demo",
                "document_session_uuid": str(uuid.uuid4()),
                "canonical_path": "/tmp/Demo.FCStd",
            },
        ),
        operation_name="Edit object",
        require_credentials=True,
    )

    assert context is not None
    assert context.to_envelope("edit_object")["lease_credentials"] == []
    conn.disconnect()


def test_authenticated_legacy_headers_never_route_document_tokens() -> None:
    conn = FreeCADConnection()
    configure_rpc_session(conn, _connected_session())

    headers = dict(
        conn._request_headers_snapshot(
            "save_document",
            (
                {
                    "document_name": "Demo",
                    "document_session_uuid": str(uuid.uuid4()),
                },
            ),
        )
    )

    assert headers["X-MCP-Lease-Credentials"] == "[]"
    assert "X-MCP-Session-Token" in headers
    assert "X-MCP-Lease-Token" not in headers
    assert "X-MCP-Lease-Id" not in headers
    assert "X-MCP-Lease-Generation" not in headers
    conn.disconnect()


def test_invoke_v2_rebuilds_legacy_context_without_document_credentials(
    monkeypatch,
) -> None:
    conn = FreeCADConnection()
    configure_rpc_session(conn, _connected_session("current-auth-secret"))
    legacy = SimpleNamespace(
        request_id=str(uuid.uuid4()),
        session_token="retired-session-secret",
        operation_name="Legacy caller",
        task_id="",
        lease_credentials=(
            SimpleNamespace(token="retired-document-secret"),
        ),
    )
    captured = {}

    def transport(conn, method, params, context, *, control, timeout):
        del conn, control, timeout
        captured["envelope"] = context.to_envelope(method, params)
        return {"ok": True, "result": {"success": True}}

    monkeypatch.setattr(connection_invoke_v2_ops, "invoke_v2_transport", transport)

    response = conn.invoke_v2("edit_object", {}, legacy)

    assert response["result"] == {"success": True}
    assert captured["envelope"]["session_token"] == "current-auth-secret"
    assert captured["envelope"]["lease_credentials"] == []
    assert "retired-document-secret" not in repr(captured)
    conn.disconnect()


def test_legacy_authority_methods_return_fresh_frozen_deprecations() -> None:
    conn = FreeCADConnection()

    first = conn.acquire_document_lock("Demo")
    second = conn.acquire_document_lock("Demo")

    assert first == {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": "Document authority is owned by native FreeCAD collaboration.",
    }
    assert second == first
    assert second is not first
    conn.disconnect()


def test_save_routes_with_authentication_only_context(monkeypatch) -> None:
    conn = FreeCADConnection()
    configure_rpc_session(conn, _connected_session())
    captured = {}

    def invoke_v2(method, params, context, *, control=False, timeout=None):
        del control, timeout
        captured["method"] = method
        captured["params"] = dict(params)
        captured["envelope"] = context.to_envelope(method, params)
        return {"ok": True, "result": {"success": True}}

    monkeypatch.setattr(conn, "invoke_v2", invoke_v2)

    result = conn.save_document(
        {"document_name": "Demo", "document_session_uuid": str(uuid.uuid4())},
        legacy_token="must-not-be-routed",
    )

    assert result == {"success": True}
    assert captured["method"] == "save_document"
    assert captured["envelope"]["lease_credentials"] == []
    assert "must-not-be-routed" not in repr(captured)

    captured.clear()
    monkeypatch.setattr(
        conn,
        "_invoke_mutation_v2",
        lambda *_args, **_kwargs: pytest.fail("release must not use RPC transport"),
    )
    release_result = conn.release_document_lock(
        "retired-document-key",
        "retired-document-secret",
        selector={"document_name": "Demo"},
    )

    assert release_result == {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": "Document authority is owned by native FreeCAD collaboration.",
    }
    assert captured == {}
    conn.disconnect()


def test_live_client_ops_do_not_import_lease_manager() -> None:
    root = Path(__file__).parents[1] / "src" / "freecad_mcp" / "freecad_client_ops"
    offenders = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and "lease_manager" in node.module
            ):
                offenders.append(path.relative_to(root).as_posix())
    assert offenders == []
