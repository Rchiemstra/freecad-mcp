"""Phase 18 contracts for native lifecycle composition."""

from __future__ import annotations

import inspect
from dataclasses import fields, replace

import pytest

from addon.FreeCADMCP.rpc_server import rpc_server
from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.lifecycle_dependencies import (
    LifecycleCollaborators,
)

pytestmark = pytest.mark.unit


def test_lifecycle_dependency_shape_is_native_and_policy_free() -> None:
    assert [field.name for field in fields(LifecycleCollaborators)] == ["freecad"]
    assert not {
        "import_document_lock",
        "import_document_lease",
        "import_core_authority",
        "document_lease_service",
        "document_identity_service",
        "save_service",
        "credential_for_selector",
        "saved_document_expectations",
        "validate_saved_document_worker",
        "refresh_lock_indicator",
    } & {field.name for field in fields(LifecycleCollaborators)}


def test_lifecycle_dependencies_validate_required_native_edge() -> None:
    collaborators = rpc_server._build_lifecycle_collaborators()
    with pytest.raises(ValueError, match="freecad collaborator is required"):
        replace(collaborators, freecad=None)


def test_default_lifecycle_graph_is_eager_and_identity_exact(monkeypatch) -> None:
    first = type(
        "FreeCADSentinel",
        (),
        {
            "getDocument": staticmethod(lambda _name: None),
            "getUserAppDataDir": staticmethod(lambda: "/profile/"),
        },
    )()
    monkeypatch.setattr(rpc_server, "FreeCAD", first)
    facade = rpc_server.FreeCADRPC()
    captured = facade._lifecycle_collaborators
    monkeypatch.setattr(rpc_server, "FreeCAD", object())

    assert facade._lifecycle_collaborators is captured
    assert captured.freecad is first
    property_source = inspect.getsource(rpc_server.FreeCADRPC._lifecycle_collaborators.fget)
    assert "_build_lifecycle_collaborators" not in property_source


def test_explicit_lifecycle_graph_is_retained_by_identity() -> None:
    collaborators = rpc_server._build_lifecycle_collaborators()
    facade = rpc_server.FreeCADRPC(lifecycle_collaborators=collaborators)
    assert facade._lifecycle_collaborators is collaborators

    with pytest.raises(TypeError, match="LifecycleCollaborators"):
        rpc_server.FreeCADRPC(lifecycle_collaborators=object())
