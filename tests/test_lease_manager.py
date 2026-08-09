from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import threading
from unittest import mock
import uuid

import pytest

from freecad_mcp.freecad_client import FreeCADConnection, RpcInvocationError
from freecad_mcp.lease_manager import (
    LeaseClientManager,
    LeaseManagerClosedError,
    LeaseCredential,
    LeaseManagerDisconnectedError,
    LeaseNotFoundError,
    RpcRequestContext,
    canonicalize_document_path,
)
from freecad_mcp.operations.core import create_document_operation
from freecad_mcp.server_state import ServerState


def _request_id(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"freecad-mcp-test:{label}"))


def _credential(session: str, token: str, *, generation: int = 1) -> LeaseCredential:
    return LeaseCredential(
        lease_id=f"lease-{session}",
        document_session_uuid=session,
        generation=generation,
        token=token,
    )


@pytest.mark.unit
def test_multi_document_concurrent_request_routing(tmp_path: Path):
    manager = LeaseClientManager(session_token="rpc-session")
    first = _credential("doc-a", "secret-a")
    second = _credential("doc-b", "secret-b", generation=4)
    path_a = tmp_path / "a.FCStd"
    path_b = tmp_path / "b.FCStd"
    manager.store(first, canonical_paths=[path_a])
    manager.store(second, canonical_paths=[path_b])

    barrier = threading.Barrier(2)

    def build(path: Path, expected_session: str):
        barrier.wait(timeout=2)
        return [
            manager.build_request_context(
                canonical_paths=[path],
                operation_name=f"edit-{expected_session}",
            ).to_envelope("edit_object", {"document": expected_session})
            for _ in range(50)
        ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        result_a = executor.submit(build, path_a, "doc-a")
        result_b = executor.submit(build, path_b, "doc-b")
        envelopes_a = result_a.result(timeout=5)
        envelopes_b = result_b.result(timeout=5)

    assert {item["lease_credentials"][0]["token"] for item in envelopes_a} == {
        "secret-a"
    }
    assert {item["lease_credentials"][0]["token"] for item in envelopes_b} == {
        "secret-b"
    }
    assert all(
        item["lease_credentials"][0]["document_session_uuid"] == "doc-a"
        for item in envelopes_a
    )
    assert all(
        item["lease_credentials"][0]["document_session_uuid"] == "doc-b"
        for item in envelopes_b
    )


@pytest.mark.unit
def test_save_as_alias_migration_is_atomic(tmp_path: Path):
    manager = LeaseClientManager(session_token="rpc-session")
    credential = _credential("doc-a", "secret-a")
    source = tmp_path / "source.FCStd"
    destination = tmp_path / "destination.FCStd"
    manager.store(credential, canonical_paths=[source])

    assert manager.migrate_alias(source, destination) is credential
    assert manager.get(canonical_path=source) is None
    assert manager.get(canonical_path=destination) is credential
    assert manager.aliases_for("doc-a") == (canonicalize_document_path(destination),)


@pytest.mark.unit
def test_credentials_and_server_state_are_redacted(tmp_path: Path):
    secret = "raw-token-must-not-leak"
    manager = LeaseClientManager(session_token="rpc-session-secret")
    credential = _credential("doc-a", secret)
    manager.store(credential, canonical_paths=[tmp_path / "model.FCStd"])

    rendered = json.dumps(manager.redacted_status(), sort_keys=True)
    assert secret not in rendered
    assert "rpc-session-secret" not in rendered
    assert secret not in repr(credential)
    assert secret not in repr(manager)

    state = ServerState(
        lease_manager=manager,
        lease_tokens={"legacy-doc": "legacy-secret"},
    )
    assert secret not in repr(state)
    assert "rpc-session-secret" not in repr(state)
    assert "legacy-secret" not in repr(state)


@pytest.mark.unit
def test_user_intervention_heartbeat_revokes_token_and_alias(tmp_path: Path):
    manager = LeaseClientManager(session_token="rpc-session")
    path = tmp_path / "model.FCStd"
    manager.store(_credential("doc-a", "secret-a"), canonical_paths=[path])

    revoked = manager.apply_heartbeat_response(
        {
            "results": [
                {
                    "document_session_uuid": "doc-a",
                    "state": "USER_INTERVENED",
                    "user_intervened": True,
                    "message": "local user took over; rejected secret-a",
                }
            ]
        }
    )

    assert len(revoked) == 1
    assert revoked[0].user_intervened is True
    assert manager.get(document_session_uuid="doc-a") is None
    assert manager.get(canonical_path=path) is None
    status = manager.redacted_status()
    assert status["revocations"][0]["reason"] == (
        "local user took over; rejected [REDACTED]"
    )
    assert "secret-a" not in json.dumps(status)


@pytest.mark.unit
def test_request_context_is_immutable_and_builds_v2_envelope():
    credential = _credential("doc-a", "secret-a", generation=8)
    context = RpcRequestContext(
        request_id=_request_id("request-1"),
        session_token="session-token",
        lease_credentials=(credential,),
        operation_name="Create Pad",
        task_id="task-1",
    )

    with pytest.raises(FrozenInstanceError):
        context.request_id = "changed"  # type: ignore[misc]

    params = {"document": {"name": "Doc"}}
    envelope = context.to_envelope("pad_feature", params)
    params["document"]["name"] = "Changed"

    assert envelope == {
        "protocol_version": 2,
        "request_id": _request_id("request-1"),
        "session_token": "session-token",
        "method": "pad_feature",
        "params": {"document": {"name": "Doc"}},
        "lease_credentials": [
            {
                "lease_id": "lease-doc-a",
                "document_session_uuid": "doc-a",
                "generation": 8,
                "token": "secret-a",
            }
        ],
        "operation": {"name": "Create Pad", "task_id": "task-1"},
    }


@pytest.mark.unit
def test_request_context_rejects_non_uuid_and_nil_request_ids():
    for invalid in ("request-1", "", str(uuid.UUID(int=0))):
        with pytest.raises(ValueError, match="request_id"):
            RpcRequestContext(
                request_id=invalid,
                session_token="session-token",
            )


@pytest.mark.unit
def test_batch_heartbeat_has_credentials_but_no_caller_owned_state():
    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(_credential("doc-b", "secret-b", generation=2))
    manager.store(_credential("doc-a", "secret-a"))

    payload = manager.build_heartbeat_payload(
        {"doc-a": "Sketch constraints", "doc-b": "Recompute"}
    )

    assert [item["document_session_uuid"] for item in payload["leases"]] == [
        "doc-a",
        "doc-b",
    ]
    assert [item["token"] for item in payload["leases"]] == [
        "secret-a",
        "secret-b",
    ]
    assert all("state" not in item for item in payload["leases"])
    assert all("document_dirty" not in item for item in payload["leases"])
    assert payload["client_monotonic_ns"].isdigit()

    atomic_payload, context = manager.build_heartbeat_request(
        request_id=_request_id("heartbeat")
    )
    assert atomic_payload["leases"][0]["token"] == "secret-a"
    assert context.request_id == _request_id("heartbeat")
    assert context.session_token == "rpc-session"
    assert context.lease_credentials == ()


@pytest.mark.unit
def test_graceful_disconnect_fences_wire_work_without_releasing():
    manager = LeaseClientManager(session_token="rpc-session")
    credential = _credential("doc-a", "secret-a")
    manager.store(credential)

    manager.mark_disconnected("FreeCAD connection closed")

    assert manager.get(document_session_uuid="doc-a") is credential
    assert manager.redacted_status()["connected"] is False
    with pytest.raises(LeaseManagerDisconnectedError):
        manager.build_request_context(document_session_uuids=["doc-a"])
    with pytest.raises(LeaseManagerDisconnectedError):
        manager.build_heartbeat_payload()


@pytest.mark.unit
def test_terminal_close_cannot_be_revived_or_accept_new_credentials():
    manager = LeaseClientManager(session_token="rpc-session-secret")
    credential = _credential("doc-a", "secret-a")
    manager.store(credential)

    manager.close("shutdown rpc-session-secret secret-a")

    status = manager.redacted_status()
    assert status["closed"] is True
    assert status["connected"] is False
    assert status["disconnect_reason"] == "shutdown [REDACTED] [REDACTED]"
    assert manager.get(document_session_uuid="doc-a") is credential
    with pytest.raises(LeaseManagerClosedError):
        manager.mark_connected("new-rpc-session")
    with pytest.raises(LeaseManagerClosedError):
        manager.store(_credential("doc-b", "secret-b"))
    with pytest.raises(LeaseManagerClosedError):
        manager.build_request_context()


@pytest.mark.unit
def test_batch_revocation_redacts_secrets_removed_earlier_in_same_response():
    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(_credential("doc-a", "secret-a"))
    manager.store(_credential("doc-b", "secret-b"))

    manager.apply_heartbeat_response(
        {
            "leases": [
                {
                    "document_session_uuid": "doc-a",
                    "revoked": True,
                    "message": "first secret-a",
                },
                {
                    "document_session_uuid": "doc-b",
                    "revoked": True,
                    "message": "both secret-a and secret-b",
                },
            ]
        }
    )

    rendered = json.dumps(manager.redacted_status(), sort_keys=True)
    assert "secret-a" not in rendered
    assert "secret-b" not in rendered
    assert rendered.count("[REDACTED]") >= 3


@pytest.mark.unit
def test_recursive_redaction_includes_retired_request_secrets():
    manager = LeaseClientManager(session_token="new-session")
    manager.store(_credential("doc-a", "current-lease-secret"))

    redacted = manager.redact_value(
        {
            "error": "old-session and current-lease-secret",
            "nested": ["current-lease-secret", {"old-session": "old-session"}],
        },
        additional_secrets=("old-session",),
    )

    rendered = json.dumps(redacted, sort_keys=True)
    assert "old-session" not in rendered
    assert "current-lease-secret" not in rendered


class _FakeProxy:
    def __init__(
        self,
        transport,
        index: int,
        calls: list[tuple[int, str, object]],
        general_started: threading.Event,
        release_general: threading.Event,
    ):
        self.transport = transport
        self.index = index
        self.calls = calls
        self.general_started = general_started
        self.release_general = release_general

    def slow_general(self):
        self.general_started.set()
        assert self.release_general.wait(timeout=3)
        return "general-complete"

    def ping(self):
        self.calls.append((self.index, "ping", None))
        return self.index

    def heartbeat(self, document: str):
        headers = dict(self.transport.extra_headers)
        self.calls.append((self.index, document, headers.get("X-MCP-Lease-Token")))
        return document

    def invoke_v2(self, envelope):
        self.calls.append((self.index, "invoke_v2", envelope))
        return {"success": True, "lane": self.index}

    def invoke_v2_control(self, envelope):
        self.calls.append((self.index, "invoke_v2_control", envelope))
        return {"success": True, "lane": self.index}


def _install_fake_proxies(monkeypatch):
    import freecad_mcp.freecad_client as client_module

    calls: list[tuple[int, str, object]] = []
    created: list[_FakeProxy] = []
    general_started = threading.Event()
    release_general = threading.Event()

    def factory(_uri, *, allow_none, transport):
        assert allow_none is True
        proxy = _FakeProxy(
            transport,
            len(created),
            calls,
            general_started,
            release_general,
        )
        created.append(proxy)
        return proxy

    monkeypatch.setattr(client_module.xmlrpc.client, "ServerProxy", factory)
    return calls, created, general_started, release_general


@pytest.mark.unit
def test_general_and_control_transports_are_isolated(monkeypatch):
    calls, created, started, release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    assert len(created) == 2
    assert connection.server.transport is not connection.control_server.transport

    thread = threading.Thread(target=connection.server.slow_general)
    thread.start()
    assert started.wait(timeout=1)
    try:
        # This would block behind slow_general if heartbeat/control reused the
        # general ServerProxy lock or HTTP transport.
        assert connection.invoke_rpc("ping", control=True) == 1
    finally:
        release.set()
        thread.join(timeout=2)
        connection.disconnect()

    assert (1, "ping", None) in calls


@pytest.mark.unit
def test_legacy_tokens_are_context_local_during_concurrent_calls(monkeypatch):
    calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    barrier = threading.Barrier(2)

    def heartbeat(document: str, token: str):
        connection.set_active_lease_token(token)
        barrier.wait(timeout=2)
        return connection.server.heartbeat(document)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(heartbeat, "doc-a", "secret-a")
        second = executor.submit(heartbeat, "doc-b", "secret-b")
        assert first.result(timeout=3) == "doc-a"
        assert second.result(timeout=3) == "doc-b"

    connection.disconnect()
    routed = {(method, token) for _, method, token in calls}
    assert routed == {("doc-a", "secret-a"), ("doc-b", "secret-b")}


@pytest.mark.unit
def test_connection_sends_v2_envelope_on_selected_lane(monkeypatch):
    calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    context = RpcRequestContext(
        request_id=_request_id("request-1"),
        session_token="rpc-session",
        lease_credentials=(_credential("doc-a", "secret-a"),),
    )

    result = connection.invoke_v2(
        "edit_object",
        {"document_session_uuid": "doc-a"},
        context,
        control=True,
    )
    connection.disconnect()

    assert result == {"success": True, "lane": 1}
    lane, method, envelope = calls[0]
    assert lane == 1
    assert method == "invoke_v2_control"
    assert envelope["request_id"] == _request_id("request-1")
    assert envelope["lease_credentials"][0]["token"] == "secret-a"


@pytest.mark.unit
def test_generated_execute_capability_is_hmac_bound_at_transport_boundary(
    monkeypatch,
):
    calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    context = RpcRequestContext(
        request_id=_request_id("signed-generated-operation"),
        session_token="rpc-session-secret",
        lease_credentials=(_credential("doc-a", "secret-a"),),
    )
    params = {
        "code": "doc.addObject('Part::Box', 'Box')",
        "options": {
            "document": "Alpha",
            "affected_documents": ["Alpha"],
            "read_only": False,
            "generated_operation": True,
            "operation_id": "create-box",
        },
    }

    connection.invoke_v2("execute_code", params, context)
    connection.disconnect()

    _lane, method, envelope = calls[0]
    assert method == "invoke_v2"
    signature = envelope["params"]["options"]["operation_signature"]
    assert signature.startswith("hmac-sha256:")
    assert "operation_signature" not in params["options"]


@pytest.mark.unit
def test_generated_mutation_uses_scoped_v2_envelope_and_caller_request_id(
    monkeypatch,
):
    _calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(_credential("doc-a", "secret-a"))
    manager.store(_credential("doc-b", "secret-b", generation=7))
    connection.configure_lease_routing(
        manager,
        lambda name: {"Alpha": "doc-a", "Beta": "doc-b"}.get(name),
    )
    envelopes = []

    def invoke(_method, params, context, **_kwargs):
        envelope = context.to_envelope(_method, params)
        envelopes.append(envelope)
        return {
            "ok": True,
            "request_id": envelope["request_id"],
            "result": {"success": True, "value": "done"},
        }

    monkeypatch.setattr(connection, "invoke_v2", invoke)
    options = {
        "document": "Alpha",
        "affected_documents": ["Alpha", "Beta"],
        "read_only": False,
        "generated_operation": True,
        "operation_id": "partdesign.create-pad",
    }

    fixed_request = _request_id("request-fixed")
    first = connection.execute_code("mutate()", options, request_id=fixed_request)
    second = connection.execute_code("mutate()", options, request_id=fixed_request)
    connection.disconnect()

    assert (
        first
        == second
        == {
            "success": True,
            "value": "done",
            "request_id": fixed_request,
        }
    )
    assert len(envelopes) == 2
    assert {item["request_id"] for item in envelopes} == {fixed_request}
    assert all(item["method"] == "execute_code" for item in envelopes)
    assert all(
        item["operation"]
        == {"name": "partdesign.create-pad", "task_id": "partdesign.create-pad"}
        for item in envelopes
    )
    assert [
        credential["document_session_uuid"]
        for credential in envelopes[0]["lease_credentials"]
    ] == ["doc-a", "doc-b"]
    assert envelopes[0]["params"]["options"]["affected_documents"] == [
        "Alpha",
        "Beta",
    ]


@pytest.mark.unit
def test_read_only_execute_remains_direct_and_has_no_v2_credential(monkeypatch):
    calls, created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(_credential("doc-a", "secret-a"))
    connection.configure_lease_routing(manager, lambda name: "doc-a")

    def direct_execute(code, options):
        headers = dict(created[0].transport.extra_headers)
        calls.append((0, "execute_code", (code, options, headers)))
        return {"success": True, "worker": True}

    monkeypatch.setattr(created[0], "execute_code", direct_execute, raising=False)
    result = connection.execute_code(
        "inspect()",
        {"document": "Alpha", "read_only": True, "execution_mode": "worker"},
    )
    connection.disconnect()

    assert result == {"success": True, "worker": True}
    _lane, _method, (_code, _options, headers) = calls[-1]
    # Compatible direct reads may authenticate the session, but do not route a
    # live mutation through invoke_v2.
    assert headers["X-MCP-Session-Token"] == "rpc-session"
    assert headers["X-MCP-Lease-Credentials"] == "[]"
    assert "X-MCP-Lease-Token" not in headers
    assert not any(call[1] == "invoke_v2" for call in calls)


@pytest.mark.unit
def test_v2_lifecycle_routes_acquire_without_credential_then_save_and_release(
    monkeypatch,
):
    _calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    manager = LeaseClientManager(session_token="rpc-session")
    credential = _credential("doc-a", "secret-a", generation=3)
    manager.store(credential)
    connection.configure_lease_routing(manager, lambda name: "doc-a")
    envelopes = []

    def invoke(method, params, context, **_kwargs):
        envelope = context.to_envelope(method, params)
        envelopes.append(envelope)
        return {"ok": True, "result": {"success": True, "method": method}}

    monkeypatch.setattr(connection, "invoke_v2", invoke)

    acquire_request = _request_id("acquire-request")
    update_request = _request_id("update-request")
    save_request = _request_id("save-request")
    release_request = _request_id("release-request")
    assert connection.acquire_document_lock(
        doc_name="Alpha", request_id=acquire_request
    )["success"]
    selector = {
        "document_session_uuid": "doc-a",
        "document_name": "Alpha",
    }
    assert connection.update_document_lock(
        selector, progress_detail="Recomputing", request_id=update_request
    )["success"]
    assert connection.save_document(selector, request_id=save_request)["success"]
    assert connection.release_document_lock(
        selector=selector, request_id=release_request
    )["success"]
    connection.disconnect()

    assert [item["method"] for item in envelopes] == [
        "acquire_document_lock",
        "update_document_lock",
        "save_document",
        "release_document_lock",
    ]
    assert envelopes[0]["request_id"] == acquire_request
    assert envelopes[0]["lease_credentials"] == []
    for envelope in envelopes[1:]:
        assert envelope["lease_credentials"][0]["token"] == "secret-a"
    assert envelopes[-1]["request_id"] == release_request


@pytest.mark.unit
def test_authenticated_create_returns_one_time_credential_without_existing_lease(
    monkeypatch,
):
    _calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    manager = LeaseClientManager(session_token="rpc-session")
    connection.configure_lease_routing(manager, lambda _name: None)
    envelopes = []
    credential = {
        "lease_id": "lease-new",
        "document_session_uuid": "doc-new",
        "generation": 1,
        "token": "one-time-new-document-token",
    }

    def invoke(method, params, context, **_kwargs):
        envelopes.append(context.to_envelope(method, params))
        return {
            "ok": True,
            "result": {
                "success": True,
                "document_name": "Fresh",
                "credential": credential,
            },
        }

    monkeypatch.setattr(connection, "invoke_v2", invoke)
    result = connection.create_document(
        "Fresh", request_id=_request_id("create-and-lease")
    )
    connection.disconnect()

    assert result["credential"] == credential
    assert envelopes[0]["method"] == "create_document"
    assert envelopes[0]["lease_credentials"] == []


@pytest.mark.unit
def test_create_document_operation_custodies_credential_and_redacts_tool_result():
    token = "one-time-new-document-token"
    freecad = mock.Mock()
    freecad.create_document.return_value = {
        "success": True,
        "document_name": "Fresh",
        "credential": {
            "lease_id": "lease-new",
            "document_session_uuid": "doc-new",
            "generation": 1,
            "token": token,
        },
    }
    manager = LeaseClientManager(session_token="rpc-session")
    document_sessions: dict[str, str] = {}

    response = create_document_operation(
        freecad,
        "Fresh",
        lease_manager=manager,
        document_sessions=document_sessions,
    )

    stored = manager.require(document_session_uuid="doc-new")
    assert stored.token == token
    assert document_sessions == {"Fresh": "doc-new"}
    assert token not in repr(response)


@pytest.mark.unit
def test_connected_v2_mutation_fails_locally_when_document_has_no_credential(
    monkeypatch,
):
    _calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    manager = LeaseClientManager(session_token="rpc-session")
    connection.configure_lease_routing(manager, lambda _name: None)

    with pytest.raises(LeaseNotFoundError):
        connection.execute_code(
            "mutate()",
            {"document": "Unleased", "read_only": False},
        )
    connection.disconnect()


@pytest.mark.unit
def test_invoke_v2_transport_headers_do_not_duplicate_envelope_secrets(monkeypatch):
    calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(
        timeout=5,
        mcp_instance_id="mcp-runtime",
        mcp_client="codex",
    )
    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(_credential("doc-a", "secret-a"))
    connection.configure_lease_routing(manager, lambda _name: "doc-a")
    connection.set_active_lease_token("legacy-secret")
    context = manager.build_request_context(
        document_session_uuids=("doc-a",), request_id=_request_id("request-1")
    )

    connection.invoke_v2("edit_object", {"doc_name": "Alpha"}, context)
    connection.disconnect()

    _lane, method, envelope = calls[0]
    assert method == "invoke_v2"
    assert envelope["session_token"] == "rpc-session"
    # The fake records only the envelope. Header behavior is asserted directly
    # because production clears transport headers immediately after each call.
    headers = dict(connection._request_headers_snapshot("invoke_v2", (envelope,)))
    assert headers["X-MCP-Instance-Id"] == "mcp-runtime"
    assert "X-MCP-Session-Token" not in headers
    assert "X-MCP-Lease-Token" not in headers
    assert "X-MCP-Request-Id" not in headers

    control_headers = dict(
        connection._request_headers_snapshot("invoke_v2_control", (envelope,))
    )
    assert control_headers == headers
    assert "X-MCP-Session-Token" not in control_headers
    assert "X-MCP-Lease-Credentials" not in control_headers
    assert "X-MCP-Lease-Token" not in control_headers
    assert "X-MCP-Request-Id" not in control_headers


@pytest.mark.unit
def test_request_status_uses_authenticated_control_lane_and_distinct_query_id(
    monkeypatch,
):
    _calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    manager = LeaseClientManager(session_token="rpc-session")
    connection.configure_lease_routing(manager, lambda _name: None)
    captured = {}

    def invoke(method, params, context, **kwargs):
        captured.update(
            method=method,
            params=params,
            envelope=context.to_envelope(method, params),
            kwargs=kwargs,
        )
        return {
            "ok": True,
            "result": {
                "success": True,
                "request_id": "mutation-request",
                "state": "completed",
            },
        }

    monkeypatch.setattr(connection, "invoke_v2", invoke)
    mutation_request = _request_id("mutation-request")
    status_query_request = _request_id("status-query-request")
    result = connection.get_request_status(
        mutation_request, request_id=status_query_request
    )
    connection.disconnect()

    assert result["state"] == "completed"
    assert captured["method"] == "get_request_status"
    assert captured["params"] == {"request_id": mutation_request}
    assert captured["envelope"]["request_id"] == status_query_request
    assert captured["envelope"]["lease_credentials"] == []
    assert captured["kwargs"]["control"] is True


@pytest.mark.unit
def test_session_rejection_refreshes_once_with_same_request_and_credentials(
    monkeypatch,
):
    _calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    manager = LeaseClientManager(session_token="expired-session")
    manager.store(_credential("doc-a", "lease-secret"))
    connection.configure_lease_routing(manager, lambda _name: "doc-a")
    refresh_count = 0
    envelopes = []

    def refresh():
        nonlocal refresh_count
        refresh_count += 1
        manager.mark_connected("refreshed-session")

    def invoke_rpc(method, envelope, **_kwargs):
        assert method == "invoke_v2"
        envelopes.append(envelope)
        if len(envelopes) == 1:
            return {
                "ok": False,
                "request_id": envelope["request_id"],
                "error": {"code": "SESSION_EXPIRED", "message": "expired"},
            }
        return {
            "ok": True,
            "request_id": envelope["request_id"],
            "result": {"success": True},
        }

    connection.configure_session_refresher(refresh)
    monkeypatch.setattr(connection, "invoke_rpc", invoke_rpc)
    context = manager.build_request_context(
        document_session_uuids=("doc-a",),
        request_id=_request_id("refresh-mutation"),
    )

    response = connection.invoke_v2("edit_object", {"doc_name": "Alpha"}, context)
    connection.disconnect()

    assert response["ok"] is True
    assert refresh_count == 1
    assert len(envelopes) == 2
    assert envelopes[0]["request_id"] == envelopes[1]["request_id"]
    assert envelopes[0]["session_token"] == "expired-session"
    assert envelopes[1]["session_token"] == "refreshed-session"
    assert envelopes[0]["lease_credentials"] == envelopes[1]["lease_credentials"]


@pytest.mark.unit
def test_authenticated_transport_exception_never_exposes_remote_fault_text(
    monkeypatch,
):
    _calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    manager = LeaseClientManager(session_token="rpc-session-secret")
    manager.store(_credential("doc-a", "lease-secret"))
    connection.configure_lease_routing(manager, lambda _name: "doc-a")
    context = manager.build_request_context(
        document_session_uuids=("doc-a",),
        request_id=_request_id("transport-fault"),
    )

    def fail(*_args, **_kwargs):
        raise RuntimeError("remote echoed rpc-session-secret and lease-secret")

    monkeypatch.setattr(connection, "invoke_rpc", fail)
    with pytest.raises(RpcInvocationError) as raised:
        connection.invoke_v2("edit_object", {"doc_name": "Alpha"}, context)
    connection.disconnect()

    rendered = str(raised.value)
    assert "rpc-session-secret" not in rendered
    assert "lease-secret" not in rendered


@pytest.mark.unit
def test_mcp_request_id_derivation_is_stable_per_call_and_avoids_payload_collision(
    monkeypatch,
):
    from mcp.server.lowlevel.server import request_ctx
    from types import SimpleNamespace

    _calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(
        timeout=5, mcp_instance_id="eb5348d7-8bc3-4a49-ad4f-b8c8d891f85e"
    )
    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(_credential("doc-a", "lease-secret"))
    connection.configure_lease_routing(manager, lambda _name: "doc-a")
    request_ids = []

    def invoke(method, params, context, **_kwargs):
        request_ids.append(context.request_id)
        return {"ok": True, "result": {"success": True}}

    monkeypatch.setattr(connection, "invoke_v2", invoke)
    context_token = request_ctx.set(SimpleNamespace(request_id="mcp-jsonrpc-42"))
    try:
        options = {"document": "Alpha", "read_only": False}
        connection.execute_code("first()", options)
        connection.execute_code("first()", options)
        connection.execute_code("second()", options)
    finally:
        request_ctx.reset(context_token)
        connection.disconnect()

    assert request_ids[0] == request_ids[1]
    assert request_ids[0] != request_ids[2]
    assert all(uuid.UUID(value).int != 0 for value in request_ids)


@pytest.mark.unit
def test_v2_public_errors_and_normal_results_are_recursively_redacted(monkeypatch):
    _calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    manager = LeaseClientManager(session_token="rpc-session-secret")
    manager.store(_credential("doc-a", "lease-secret"))
    connection.configure_lease_routing(manager, lambda _name: "doc-a")

    failed = connection._unwrap_v2_response(
        {
            "ok": False,
            "error": {
                "code": "DENIED",
                "message": "rpc-session-secret lease-secret",
            },
        }
    )
    succeeded = connection._unwrap_v2_response(
        {
            "ok": True,
            "result": {"success": True, "message": "echo lease-secret"},
        }
    )
    acquisition = connection._unwrap_v2_response(
        {
            "ok": True,
            "result": {
                "success": True,
                "credential": {"token": "new-acquisition-secret"},
            },
        }
    )
    connection.disconnect()

    assert "rpc-session-secret" not in json.dumps(failed)
    assert "lease-secret" not in json.dumps(failed)
    assert succeeded["message"] == "echo [REDACTED]"
    assert acquisition["credential"]["token"] == "new-acquisition-secret"


@pytest.mark.unit
def test_connection_disconnect_fences_manager_and_is_idempotent(monkeypatch):
    _calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(_credential("doc-a", "lease-secret"))
    connection.configure_lease_routing(manager, lambda _name: "doc-a")

    connection.disconnect()
    connection.disconnect()

    assert manager.redacted_status()["connected"] is False
    assert manager.get(document_session_uuid="doc-a") is not None
    with pytest.raises(LeaseManagerDisconnectedError):
        manager.build_request_context(document_session_uuids=("doc-a",))


@pytest.mark.unit
def test_disconnect_closes_both_lanes_and_sanitizes_close_failure(monkeypatch):
    _calls, _created, _started, _release = _install_fake_proxies(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    manager = LeaseClientManager(session_token="rpc-session-secret")
    connection.configure_lease_routing(manager, lambda _name: None)
    general = mock.Mock(side_effect=RuntimeError("rpc-session-secret"))
    control = mock.Mock()
    monkeypatch.setattr(connection.server, "close", general)
    monkeypatch.setattr(connection.control_server, "close", control)

    with pytest.raises(RpcInvocationError) as raised:
        connection.disconnect()

    general.assert_called_once_with()
    control.assert_called_once_with()
    assert "rpc-session-secret" not in str(raised.value)
    assert manager.connected is False
