"""Contracts for the policy-free installed collaboration client."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any

import pytest

import freecad_mcp.collaboration_client as collaboration_module
from freecad_mcp.collaboration_client import CollaborationClient


class _Connection:
    def __init__(self, label: str) -> None:
        self.label = label
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.results: dict[str, object] = {}

    def _record(self, name: str, *args: object, **kwargs: object) -> object:
        self.calls.append((name, args, kwargs))
        return self.results.setdefault(name, object())

    def acquire_document_lock(self, *args: object, **kwargs: object) -> dict[str, Any]:
        return self._record("acquire_document_lock", *args, **kwargs)

    def adopt_dirty_document(self, *args: object, **kwargs: object) -> dict[str, Any]:
        return self._record("adopt_dirty_document", *args, **kwargs)

    def get_request_status(self, *args: object, **kwargs: object) -> dict[str, Any]:
        return self._record("get_request_status", *args, **kwargs)

    def claim_acquisition_result(self, *args: object, **kwargs: object) -> dict[str, Any]:
        return self._record("claim_acquisition_result", *args, **kwargs)

    def acknowledge_acquisition_claim(
        self, *args: object, **kwargs: object
    ) -> dict[str, Any]:
        return self._record("acknowledge_acquisition_claim", *args, **kwargs)

    def cancel_request(self, *args: object, **kwargs: object) -> dict[str, Any]:
        return self._record("cancel_request", *args, **kwargs)

    def reconcile_document_lease(
        self, *args: object, **kwargs: object
    ) -> dict[str, Any]:
        return self._record("reconcile_document_lease", *args, **kwargs)

    def stale_recovery_status(self) -> dict[str, Any]:
        return self._record("stale_recovery_status")


def test_collaboration_client_delegates_acquisition_and_adoption_without_rewriting():
    connection = _Connection("initial")
    client = CollaborationClient(connection)  # type: ignore[arg-type]
    selector = {"document_name": "Document", "nested": {"id": 3}}

    assert client.connection is connection
    assert client.acquire_document_lock(
        "Document",
        "/tmp/Document.FCStd",
        "legacy-session",
        "Task",
        "legacy-client",
        selector,
        "legacy-agent",
        "sha256",
        "request-1",
    ) is connection.results["acquire_document_lock"]
    assert client.adopt_dirty_document(
        selector=selector,
        task_description="Adopt",
        client="legacy-client",
        agent_id="legacy-agent",
        hash_policy="sha256",
        request_id="request-2",
    ) is connection.results["adopt_dirty_document"]

    assert connection.calls == [
        (
            "acquire_document_lock",
            (
                "Document",
                "/tmp/Document.FCStd",
                "legacy-session",
                "Task",
                "legacy-client",
                selector,
                "legacy-agent",
                "sha256",
                "request-1",
            ),
            {},
        ),
        (
            "adopt_dirty_document",
            (),
            {
                "selector": selector,
                "task_description": "Adopt",
                "client": "legacy-client",
                "agent_id": "legacy-agent",
                "hash_policy": "sha256",
                "request_id": "request-2",
            },
        ),
    ]


def test_collaboration_client_delegates_handoff_recovery_and_cancellation_exactly_once():
    connection = _Connection("initial")
    client = CollaborationClient(connection)  # type: ignore[arg-type]

    assert client.get_request_status("target", request_id="status") is connection.results[
        "get_request_status"
    ]
    assert client.claim_acquisition_result(
        "target", request_id="claim"
    ) is connection.results["claim_acquisition_result"]
    assert client.acknowledge_acquisition_claim(
        "target", request_id="ack"
    ) is connection.results["acknowledge_acquisition_claim"]
    assert client.cancel_request("target", request_id="cancel") is connection.results[
        "cancel_request"
    ]
    assert client.reconcile_document_lease(
        "document-session", request_id="recover"
    ) is connection.results["reconcile_document_lease"]
    assert client.stale_recovery_status() is connection.results["stale_recovery_status"]

    assert connection.calls == [
        ("get_request_status", ("target",), {"request_id": "status"}),
        ("claim_acquisition_result", ("target",), {"request_id": "claim"}),
        ("acknowledge_acquisition_claim", ("target",), {"request_id": "ack"}),
        ("cancel_request", ("target",), {"request_id": "cancel"}),
        (
            "reconcile_document_lease",
            ("document-session",),
            {"request_id": "recover"},
        ),
        ("stale_recovery_status", (), {}),
    ]


def test_rebind_preserves_client_identity_and_routes_only_future_calls_to_replacement():
    initial = _Connection("initial")
    replacement = _Connection("replacement")
    client = CollaborationClient(initial)  # type: ignore[arg-type]

    client.get_request_status("before")
    assert client.rebind(replacement) is None  # type: ignore[arg-type]
    assert client.connection is replacement
    client.get_request_status("after")

    assert initial.calls == [("get_request_status", ("before",), {"request_id": None})]
    assert replacement.calls == [
        ("get_request_status", ("after",), {"request_id": None})
    ]


@pytest.mark.parametrize(
    ("name", "invoke"),
    (
        (
            "acquire_document_lock",
            lambda client: client.acquire_document_lock(doc_name="Document"),
        ),
        (
            "adopt_dirty_document",
            lambda client: client.adopt_dirty_document(selector={"document_name": "Document"}),
        ),
        ("get_request_status", lambda client: client.get_request_status("request")),
        (
            "claim_acquisition_result",
            lambda client: client.claim_acquisition_result("request"),
        ),
        (
            "acknowledge_acquisition_claim",
            lambda client: client.acknowledge_acquisition_claim("request"),
        ),
        ("cancel_request", lambda client: client.cancel_request("request")),
        (
            "reconcile_document_lease",
            lambda client: client.reconcile_document_lease("document-session"),
        ),
        ("stale_recovery_status", lambda client: client.stale_recovery_status()),
    ),
)
def test_client_preserves_each_connection_result_and_exception_identity(name, invoke):
    connection = _Connection("initial")
    client = CollaborationClient(connection)  # type: ignore[arg-type]
    result = object()
    connection.results[name] = result

    assert invoke(client) is result

    expected = RuntimeError(name)

    def raise_expected(*_args: object, **_kwargs: object) -> object:
        raise expected

    setattr(connection, name, raise_expected)
    with pytest.raises(RuntimeError) as raised:
        invoke(client)
    assert raised.value is expected


def test_client_rejects_an_incomplete_connection_before_any_rpc_can_be_sent():
    class IncompleteConnection:
        def acquire_document_lock(self) -> None:
            pass

    try:
        CollaborationClient(IncompleteConnection())  # type: ignore[arg-type]
    except TypeError as exc:
        assert str(exc) == (
            "CollaborationClient requires a FreeCADConnection-compatible dependency; "
            "missing adopt_dirty_document, get_request_status, "
            "claim_acquisition_result, acknowledge_acquisition_claim, cancel_request, "
            "reconcile_document_lease, stale_recovery_status"
        )
    else:
        raise AssertionError("incomplete injected connection was accepted")


def test_failed_rebind_keeps_the_original_connection_and_connection_property_read_only():
    initial = _Connection("initial")
    client = CollaborationClient(initial)  # type: ignore[arg-type]
    malformed = _Connection("malformed")
    malformed.cancel_request = None  # type: ignore[method-assign]

    with pytest.raises(TypeError, match="missing cancel_request"):
        client.rebind(malformed)  # type: ignore[arg-type]

    assert client.connection is initial
    assert client.get_request_status("still-initial") is initial.results[
        "get_request_status"
    ]
    with pytest.raises(AttributeError):
        client.connection = malformed  # type: ignore[misc]


def test_client_public_methods_keep_the_connection_call_signatures():
    from freecad_mcp.freecad_client import FreeCADConnection

    for name in (
        "acquire_document_lock",
        "adopt_dirty_document",
        "get_request_status",
        "claim_acquisition_result",
        "acknowledge_acquisition_claim",
        "cancel_request",
        "reconcile_document_lease",
        "stale_recovery_status",
    ):
        client_parameters = tuple(
            inspect.signature(getattr(CollaborationClient, name)).parameters.values()
        )[1:]
        connection_parameters = tuple(
            inspect.signature(getattr(FreeCADConnection, name)).parameters.values()
        )[1:]
        assert client_parameters == connection_parameters


def test_client_dependency_and_call_boundary_is_strictly_limited():
    source = Path(inspect.getfile(CollaborationClient)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [
        (node.module or "", tuple(alias.name for alias in node.names))
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    ]
    direct_imports = [
        tuple(alias.name for alias in node.names)
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
    ]

    assert direct_imports == []
    assert sorted(imports) == [
        ("__future__", ("annotations",)),
        ("collections.abc", ("Mapping",)),
        ("typing", ("Any", "Protocol")),
    ]

    def call_target(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Attribute):
                return f"{call_target(node.value)}.{node.attr}"
            if isinstance(node.value, ast.Name):
                return f"{node.value.id}.{node.attr}"
            if isinstance(node.value, ast.Constant):
                return f"literal.{node.attr}"
        return "<dynamic>"

    assert sorted(
        call_target(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
    ) == sorted(
        (
            "TypeError",
            "callable",
            "getattr",
            "literal.join",
            "self._validate_connection",
            "self._validate_connection",
            "self._connection.acquire_document_lock",
            "self._connection.adopt_dirty_document",
            "self._connection.get_request_status",
            "self._connection.claim_acquisition_result",
            "self._connection.acknowledge_acquisition_claim",
            "self._connection.cancel_request",
            "self._connection.reconcile_document_lease",
            "self._connection.stale_recovery_status",
        )
    )

    connection_methods = (
        "acquire_document_lock",
        "adopt_dirty_document",
        "get_request_status",
        "claim_acquisition_result",
        "acknowledge_acquisition_claim",
        "cancel_request",
        "reconcile_document_lease",
        "stale_recovery_status",
    )
    assert collaboration_module.__all__ == ["CollaborationClient"]
    assert collaboration_module._CONNECTION_METHODS == connection_methods
    assert set(CollaborationClient.__dict__) == {
        "__module__",
        "__doc__",
        "__init__",
        "__dict__",
        "__weakref__",
        "connection",
        "rebind",
        "_validate_connection",
        *connection_methods,
    }

    attribute_targets = {
        call_target(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }
    assert attribute_targets == {
        "literal.join",
        "self._connection",
        "self._validate_connection",
        *(f"self._connection.{name}" for name in connection_methods),
    }
    assert sorted(
        call_target(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store)
    ) == ["self._connection", "self._connection"]

    def store_target(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return call_target(node)
        if isinstance(node, ast.Subscript):
            return f"{call_target(node.value)}[subscript]"
        return f"<{type(node).__name__}>"

    assert sorted(
        store_target(node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript))
        and isinstance(node.ctx, ast.Store)
    ) == [
        "_CONNECTION_METHODS",
        "__all__",
        "missing",
        "name",
        "self._connection",
        "self._connection",
    ]
    assert not any(
        isinstance(node, (ast.Global, ast.Nonlocal)) for node in ast.walk(tree)
    )
