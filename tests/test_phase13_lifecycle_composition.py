"""Phase 13 contracts for eager lifecycle collaborator composition."""

from __future__ import annotations

import inspect
from dataclasses import fields, replace

import pytest

from addon.FreeCADMCP.rpc_server import rpc_server
from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.lifecycle_dependencies import (
    LifecycleCollaborators,
)

pytestmark = pytest.mark.unit


def test_lifecycle_dependency_shape_is_explicit_and_policy_free() -> None:
    assert [field.name for field in fields(LifecycleCollaborators)] == [
        "freecad",
        "import_document_lock",
        "import_document_lease",
        "import_core_authority",
        "document_lease_service",
        "document_identity_service",
        "save_service",
        "credential_for_selector",
        "live_document_from_selector",
        "ensure_v2_document",
        "live_validation_evidence",
        "discard_terminal_snapshot",
        "saved_document_expectations",
        "validate_saved_document_worker",
        "inspect_references_gui",
        "redact_rpc_diagnostic",
        "lease_service_error",
        "deprecated_force_release_result",
        "refresh_lock_indicator",
    ]
    assert not {
        "dirty_state",
        "persisted_state",
        "recovery_policy",
        "sidecar_policy",
        "lease_owner",
        "token",
        "generation",
    } & {field.name for field in fields(LifecycleCollaborators)}


def test_lifecycle_dependencies_validate_required_edges() -> None:
    collaborators = rpc_server._build_lifecycle_collaborators()
    with pytest.raises(ValueError, match="freecad collaborator is required"):
        replace(collaborators, freecad=None)
    with pytest.raises(TypeError, match="refresh_lock_indicator"):
        replace(collaborators, refresh_lock_indicator=None)


def test_default_lifecycle_graph_is_eager_and_identity_exact(monkeypatch) -> None:
    lease_service = object()
    identity_service = object()
    save_service = object()
    monkeypatch.setattr(rpc_server, "document_lease_service", lease_service)
    monkeypatch.setattr(rpc_server, "document_identity_service", identity_service)
    monkeypatch.setattr(rpc_server, "save_service", save_service)

    facade = rpc_server.FreeCADRPC()
    captured = facade._lifecycle_collaborators

    monkeypatch.setattr(rpc_server, "document_lease_service", object())
    monkeypatch.setattr(rpc_server, "document_identity_service", object())
    monkeypatch.setattr(rpc_server, "save_service", object())

    assert facade._lifecycle_collaborators is captured
    assert captured.document_lease_service is lease_service
    assert captured.document_identity_service is identity_service
    assert captured.save_service is save_service
    assert captured.freecad is rpc_server.FreeCAD
    assert captured.credential_for_selector is rpc_server._credential_for_selector
    assert captured.live_document_from_selector is rpc_server._live_document_from_selector
    assert captured.ensure_v2_document is rpc_server._ensure_v2_document
    assert captured.inspect_references_gui is rpc_server.inspect_references_gui
    assert (
        captured.deprecated_force_release_result
        is rpc_server._deprecated_force_release_result
    )

    property_source = inspect.getsource(
        rpc_server.FreeCADRPC._lifecycle_collaborators.fget
    )
    assert "_build_lifecycle_collaborators" not in property_source


def test_explicit_lifecycle_graph_is_retained_by_identity() -> None:
    collaborators = rpc_server._build_lifecycle_collaborators()
    facade = rpc_server.FreeCADRPC(lifecycle_collaborators=collaborators)
    assert facade._lifecycle_collaborators is collaborators

    with pytest.raises(TypeError, match="LifecycleCollaborators"):
        rpc_server.FreeCADRPC(lifecycle_collaborators=object())
