"""Phase 18 create-document authority cutover regressions."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.lifecycle_methods_ops import document_create
from freecad_mcp.operations.core_ops.document_ops import create_document_operation

pytestmark = pytest.mark.unit


class _CaptureMcp:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):
        def decorate(function):
            self.tools[function.__name__] = function
            return function

        return decorate


class _RemovedLeaseState:
    def __getattr__(self, name: str):
        raise AssertionError(f"registered tool read removed ServerState field {name!r}")


class _CreateBackend:
    def __init__(self) -> None:
        self.names: list[str] = []

    def create_document(self, name: str) -> dict[str, object]:
        self.names.append(name)
        return {
            "success": True,
            "document_name": name,
            "request_id": "historic-request",
            "credential": {
                "lease_id": "historic-lease",
                "document_session_uuid": "historic-document-session",
                "generation": 1,
                "token": "must-not-cross-tool-boundary",
            },
        }

    def acknowledge_acquisition_claim(self, _request_id: str) -> None:
        raise AssertionError("MCP must not acknowledge a historic acquisition claim")


def test_registered_create_document_uses_no_removed_server_state(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from freecad_mcp import tools_core_document
    from freecad_mcp.collaboration_client import CollaborationClient
    from freecad_mcp.server_ops.tool_dependencies import ToolDependencies

    backend = _CreateBackend()
    mcp = _CaptureMcp()
    monkeypatch.setattr(tools_core_document, "server_connection", lambda: backend)

    dependencies = ToolDependencies(
        state=_RemovedLeaseState(),
        get_freecad_connection=lambda: backend,
        recovery_compatibility=None,
        collaboration=CollaborationClient(MagicMock()),
        document_selector_input=dict,
    )
    exports = tools_core_document.register(mcp, dependencies=dependencies)
    result = exports["create_document"](None, "NativeDocument")

    assert backend.names == ["NativeDocument"]
    assert result.structuredContent["data"] == {
        "success": True,
        "document_name": "NativeDocument",
        "request_id": "historic-request",
        "credential_stored": False,
        "token_exported": False,
    }


def test_create_operation_has_no_credential_custody_collaborators() -> None:
    assert tuple(inspect.signature(create_document_operation).parameters) == (
        "freecad",
        "name",
    )

    result = create_document_operation(_CreateBackend(), "NativeDocument")
    serialized = repr(result.structuredContent)

    assert "must-not-cross-tool-boundary" not in serialized
    assert "historic-lease" not in serialized
    assert result.structuredContent["data"]["credential_stored"] is False


def test_create_lookup_and_evidence_stay_inside_gui_dispatch(monkeypatch) -> None:
    state = {"inside_dispatch": False}
    document = SimpleNamespace(Name="NativeDocument")

    def require_dispatch(value):
        assert state["inside_dispatch"] is True
        return value

    monkeypatch.setattr(
        document_create,
        "FreeCAD",
        SimpleNamespace(getDocument=lambda name: require_dispatch(document)),
    )

    def dispatch(callback):
        state["inside_dispatch"] = True
        try:
            result = callback()
            assert not any(value is document for value in result.values())
            return result
        finally:
            state["inside_dispatch"] = False

    facade = SimpleNamespace(
        _request_checkpoint=lambda checkpoint: checkpoint,
        _create_document_gui=lambda name: require_dispatch(True),
        _observed_document_evidence=lambda operation, observed, **kwargs: (
            require_dispatch(
                {
                    "document_health": {
                        "verdict": "valid",
                        "document_name": observed.Name,
                    }
                }
            )
        ),
        _unknown_mutation_evidence=lambda *args, **kwargs: {
            "document_health": {"verdict": "unknown"}
        },
        _dispatch_gui=dispatch,
    )

    result = document_create.create_document(facade, "NativeDocument")

    assert result["success"] is True
    assert result["document_health"] == {
        "verdict": "valid",
        "document_name": "NativeDocument",
    }
    assert state["inside_dispatch"] is False
