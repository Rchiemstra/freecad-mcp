"""Phase 18 contracts for native collaboration composition."""

from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, fields

import pytest

from addon.FreeCADMCP.rpc_server import rpc_server
from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.collaboration_dependencies import (
    CollaborationCollaborators,
)

pytestmark = pytest.mark.unit


class _CompatibilityAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []
        self.result = object()

    def commit_compatibility_mutation(self, document_name, callback):
        self.calls.append((document_name, callback))
        return self.result


def _collaborators(**overrides):
    values = {
        "compatibility_api": _CompatibilityAPI(),
        "freecad": object(),
        "runtime_manifest": None,
        "inflight_request_registry": object(),
        "request_replay_cache": object(),
        "rpc_server_runtime_id": "addon-runtime",
        "addon_loaded_at": "loaded-at",
    }
    values.update(overrides)
    return CollaborationCollaborators(**values)


def test_collaboration_graph_is_native_auth_only_and_immutable() -> None:
    expected = [
        "compatibility_api",
        "freecad",
        "runtime_manifest",
        "inflight_request_registry",
        "request_replay_cache",
        "rpc_server_runtime_id",
        "addon_loaded_at",
    ]
    collaborators = _collaborators()

    assert [field.name for field in fields(CollaborationCollaborators)] == expected
    assert not {
        "document_lease_service",
        "document_identity_service",
        "acquisition_claim_store",
        "handoff_continuation_store",
        "import_document_lock",
        "import_document_lease",
        "credential_from_wire",
        "create_lease_baseline_snapshot_gui",
    } & set(expected)
    with pytest.raises(FrozenInstanceError):
        collaborators.freecad = object()


def test_runtime_manifest_binding_is_exact_idempotent_and_single_assignment() -> None:
    collaborators = _collaborators()
    manifest = object()

    bound = collaborators.with_runtime_manifest(manifest)

    assert bound is not collaborators
    assert bound.runtime_manifest is manifest
    assert bound.with_runtime_manifest(manifest) is bound
    with pytest.raises(RuntimeError, match="already bound"):
        bound.with_runtime_manifest(object())
    with pytest.raises(ValueError, match="required"):
        collaborators.with_runtime_manifest(None)


def test_no_arg_facade_captures_collaborators_eagerly() -> None:
    facade = rpc_server.FreeCADRPC()
    captured = facade._collaboration_collaborators

    assert facade._collaboration_collaborators is captured
    assert captured.freecad is rpc_server.FreeCAD
    source = inspect.getsource(rpc_server.FreeCADRPC._collaboration_collaborators.fget)
    assert "_build_collaboration_collaborators" not in source


def test_factory_fails_closed_for_missing_native_dependencies() -> None:
    with pytest.raises(ValueError, match="freecad collaborator is required"):
        _collaborators(freecad=None)
    with pytest.raises(TypeError, match="commit_compatibility_mutation"):
        _collaborators(compatibility_api=object())


def test_compatibility_mutation_uses_the_exact_injected_route_once() -> None:
    api = _CompatibilityAPI()
    collaborators = _collaborators(compatibility_api=api)
    document_name = "Model"

    def callback():
        return None

    actual = collaborators.commit_compatibility_mutation(document_name, callback)

    assert actual is api.result
    assert api.calls == [(document_name, callback)]
