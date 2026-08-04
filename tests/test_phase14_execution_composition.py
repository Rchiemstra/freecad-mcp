"""Phase 14 contracts for eager execution collaborator composition."""

from __future__ import annotations

import inspect
from dataclasses import fields, replace
from pathlib import Path

import pytest

from addon.FreeCADMCP.rpc_server import rpc_server
from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.execution_dependencies import (
    ExecutionCollaborators,
)

pytestmark = pytest.mark.unit


def test_execution_dependency_shape_is_explicit_and_policy_free() -> None:
    assert [field.name for field in fields(ExecutionCollaborators)] == [
        "compatibility_api",
        "freecad",
        "gui_dispatcher",
        "worker_manager",
        "snapshot_coordinator",
        "shutdown_requested",
        "request_replay_cache",
        "inflight_request_registry",
        "acquisition_claim_store",
        "handoff_continuation_store",
        "document_lease_service",
        "document_identity_service",
        "session_manager",
        "runtime_manifest",
        "actual_endpoint",
        "runtime_id",
        "server_started_at",
        "addon_loaded_at",
        "execute_timeout",
        "logger",
        "stop_rpc_server",
        "import_document_lock",
        "import_document_lease",
        "credential_for_document",
        "credential_from_wire",
        "redact_rpc_diagnostic",
        "lease_service_error",
        "lease_protocol_public_error",
        "external_scope_block",
        "assert_mutation_file_metadata_unchanged",
        "generated_execute_signature",
        "generated_operation_method_spec",
        "validate_generated_operation_envelope",
        "snapshot_mutation_context_for_request",
        "create_primary_snapshot_gui",
        "freecad_version_parts",
        "load_settings",
        "analyze_execute_code",
        "typed_tool_warning",
        "find_gui_geometry_loop_risk",
        "find_gui_blocking_risk",
        "process_started_at",
        "boot_id",
        "profile_fingerprint",
    ]
    assert not {
        "dirty_state",
        "persisted_state",
        "recovery_policy",
        "sidecar_policy",
        "credential_policy",
        "lease_owner",
        "token",
        "generation",
    } & {field.name for field in fields(ExecutionCollaborators)}


def test_execution_dependencies_validate_required_edges() -> None:
    collaboration = rpc_server._build_collaboration_collaborators()
    collaborators = rpc_server._build_execution_collaborators(
        compatibility_api=collaboration.compatibility_api
    )

    with pytest.raises(ValueError, match="freecad collaborator is required"):
        replace(collaborators, freecad=None)
    with pytest.raises(ValueError, match="snapshot_coordinator"):
        replace(collaborators, snapshot_coordinator=None)
    with pytest.raises(ValueError, match="non-negative"):
        replace(collaborators, execute_timeout=-1)
    with pytest.raises(TypeError, match="find_gui_blocking_risk"):
        replace(collaborators, find_gui_blocking_risk=None)


def test_default_execution_graph_is_eager_exact_and_shares_native_api(
    monkeypatch,
) -> None:
    dispatcher = object()
    manager = object()
    replay = object()
    monkeypatch.setattr(rpc_server, "gui_dispatcher", dispatcher)
    monkeypatch.setattr(rpc_server, "worker_manager", manager)
    monkeypatch.setattr(rpc_server, "rpc_request_replay_cache", replay)

    facade = rpc_server.FreeCADRPC()
    captured = facade._execution_collaborators

    monkeypatch.setattr(rpc_server, "gui_dispatcher", object())
    monkeypatch.setattr(rpc_server, "worker_manager", object())
    monkeypatch.setattr(rpc_server, "rpc_request_replay_cache", object())

    assert facade._execution_collaborators is captured
    assert captured.gui_dispatcher is dispatcher
    assert captured.worker_manager is manager
    assert captured.request_replay_cache is replay
    assert (
        captured.compatibility_api
        is facade._collaboration_collaborators.compatibility_api
    )
    property_source = inspect.getsource(
        rpc_server.FreeCADRPC._execution_collaborators.fget
    )
    assert "_build_execution_collaborators" not in property_source


def test_explicit_execution_graph_requires_the_shared_native_api() -> None:
    collaboration = rpc_server._build_collaboration_collaborators()
    collaborators = rpc_server._build_execution_collaborators(
        compatibility_api=collaboration.compatibility_api
    )
    facade = rpc_server.FreeCADRPC(
        collaboration_collaborators=collaboration,
        execution_collaborators=collaborators,
    )
    assert facade._execution_collaborators is collaborators

    with pytest.raises(TypeError, match="ExecutionCollaborators"):
        rpc_server.FreeCADRPC(execution_collaborators=object())
    mismatched = rpc_server._build_execution_collaborators(
        compatibility_api=rpc_server._CollaborationAPI(
            document_lookup=rpc_server.FreeCAD.getDocument
        )
    )
    with pytest.raises(ValueError, match="share compatibility_api"):
        rpc_server.FreeCADRPC(
            collaboration_collaborators=collaboration,
            execution_collaborators=mismatched,
        )


def test_authenticated_runtime_binding_is_exact_and_single_assignment() -> None:
    collaboration = rpc_server._build_collaboration_collaborators()
    collaborators = rpc_server._build_execution_collaborators(
        compatibility_api=collaboration.compatibility_api
    )
    session = object()
    manifest = object()
    endpoint = {"host": "127.0.0.1", "port": 19875}

    bound = collaborators.with_authenticated_runtime(
        session_manager=session,
        runtime_manifest=manifest,
        actual_endpoint=endpoint,
        server_started_at="started",
    )

    assert bound.session_manager is session
    assert bound.runtime_manifest is manifest
    assert bound.actual_endpoint is endpoint
    assert bound.with_authenticated_runtime(
        session_manager=session,
        runtime_manifest=manifest,
        actual_endpoint=endpoint,
        server_started_at="started",
    ) is bound
    with pytest.raises(RuntimeError, match="session_manager"):
        bound.with_authenticated_runtime(
            session_manager=object(),
            runtime_manifest=manifest,
            actual_endpoint=endpoint,
            server_started_at="started",
        )


def test_reconcile_helper_has_no_runtime_locator() -> None:
    path = (
        Path(rpc_server.__file__).parent
        / "rpc_helpers_ops"
        / "reconcile.py"
    )
    source = path.read_text(encoding="utf-8")
    assert "_rpc_mod" not in source
