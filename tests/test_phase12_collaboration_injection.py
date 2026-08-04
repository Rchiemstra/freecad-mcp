"""Phase 12 contracts for explicit lease-operation collaborators."""

from __future__ import annotations

import ast
import inspect
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.acquire import (
    acquire_document_lock,
    adopt_dirty_document,
)
from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.acquire_v2_helpers import (
    handle_snapshot_timeout,
)
from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.acquisition_claims_helpers import (
    claim_handoff_continuation,
)
from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.collaboration_dependencies import (
    CollaborationCollaborators,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "addon" / "FreeCADMCP" / "rpc_server" / "methods" / "lease_methods_ops"


class _CompatibilityAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []
        self.result = object()

    def commit_compatibility_mutation(self, document_name, callback):
        self.calls.append((document_name, callback))
        return self.result


def _callable(*_args, **_kwargs):
    return None


def _runtime(**overrides):
    values = {
        "FreeCAD": object(),
        "_import_document_lock": _callable,
        "_import_document_lease": _callable,
        "document_lease_service": object(),
        "document_identity_service": object(),
        "rpc_runtime_manifest": object(),
        "rpc_inflight_request_registry": object(),
        "rpc_acquisition_claim_store": object(),
        "rpc_handoff_continuation_store": object(),
        "rpc_request_replay_cache": object(),
        "rpc_server_runtime_id": "addon-runtime",
        "addon_loaded_at": "loaded-at",
        "_redact_rpc_diagnostic": _callable,
        "_lease_service_error": _callable,
        "_live_document_from_selector": _callable,
        "_confirm_dirty_document_adoption_gui": _callable,
        "_authorize_locked_error_handoff_gui": _callable,
        "create_lease_baseline_snapshot_gui": _callable,
        "discard_lease_baseline_snapshot": _callable,
        "_credential_from_wire": _callable,
        "_stale_reconcile_already_recovered": _callable,
        "_stale_reconcile_classify": _callable,
        "_assert_mutation_file_metadata_unchanged": _callable,
        "_assert_never_saved_stale_continuity": _callable,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _collaborators(**overrides):
    compatibility_api = overrides.pop("compatibility_api", _CompatibilityAPI())
    runtime = _runtime(**overrides)
    return CollaborationCollaborators(
        compatibility_api=compatibility_api,
        freecad=runtime.FreeCAD,
        import_document_lock=runtime._import_document_lock,
        import_document_lease=runtime._import_document_lease,
        document_lease_service=runtime.document_lease_service,
        document_identity_service=runtime.document_identity_service,
        runtime_manifest=runtime.rpc_runtime_manifest,
        inflight_request_registry=runtime.rpc_inflight_request_registry,
        acquisition_claim_store=runtime.rpc_acquisition_claim_store,
        handoff_continuation_store=runtime.rpc_handoff_continuation_store,
        request_replay_cache=runtime.rpc_request_replay_cache,
        rpc_server_runtime_id=runtime.rpc_server_runtime_id,
        addon_loaded_at=runtime.addon_loaded_at,
        redact_rpc_diagnostic=runtime._redact_rpc_diagnostic,
        lease_service_error=runtime._lease_service_error,
        live_document_from_selector=runtime._live_document_from_selector,
        confirm_dirty_document_adoption_gui=(
            runtime._confirm_dirty_document_adoption_gui
        ),
        authorize_locked_error_handoff_gui=(
            runtime._authorize_locked_error_handoff_gui
        ),
        create_lease_baseline_snapshot_gui=(
            runtime.create_lease_baseline_snapshot_gui
        ),
        discard_lease_baseline_snapshot=runtime.discard_lease_baseline_snapshot,
        credential_from_wire=runtime._credential_from_wire,
        stale_reconcile_already_recovered=(
            runtime._stale_reconcile_already_recovered
        ),
        stale_reconcile_classify=runtime._stale_reconcile_classify,
        assert_mutation_file_metadata_unchanged=(
            runtime._assert_mutation_file_metadata_unchanged
        ),
        assert_never_saved_stale_continuity=(
            runtime._assert_never_saved_stale_continuity
        ),
    )


def test_factory_captures_exact_dependency_identities_and_is_immutable() -> None:
    service = object()
    identity_service = object()
    claim_store = object()
    compatibility_api = _CompatibilityAPI()

    collaborators = _collaborators(
        compatibility_api=compatibility_api,
        document_lease_service=service,
        document_identity_service=identity_service,
        rpc_acquisition_claim_store=claim_store,
    )

    assert collaborators.compatibility_api is compatibility_api
    assert collaborators.document_lease_service is service
    assert collaborators.document_identity_service is identity_service
    assert collaborators.acquisition_claim_store is claim_store
    with pytest.raises(FrozenInstanceError):
        collaborators.document_lease_service = object()


def test_runtime_manifest_binding_is_exact_idempotent_and_single_assignment() -> None:
    collaborators = _collaborators(rpc_runtime_manifest=None)
    manifest = object()

    bound = collaborators.with_runtime_manifest(manifest)

    assert bound is not collaborators
    assert bound.runtime_manifest is manifest
    assert bound.with_runtime_manifest(manifest) is bound
    with pytest.raises(RuntimeError, match="already bound"):
        bound.with_runtime_manifest(object())
    with pytest.raises(ValueError, match="required"):
        collaborators.with_runtime_manifest(None)


def test_no_arg_facade_captures_collaborators_eagerly(monkeypatch) -> None:
    from addon.FreeCADMCP.rpc_server import rpc_server

    initial_service = object()
    replacement_service = object()
    monkeypatch.setattr(rpc_server, "document_lease_service", initial_service)

    facade = rpc_server.FreeCADRPC()
    monkeypatch.setattr(rpc_server, "document_lease_service", replacement_service)

    assert facade._collaboration_collaborators.document_lease_service is initial_service
    source = inspect.getsource(
        rpc_server.FreeCADRPC._collaboration_collaborators.fget
    )
    assert "_build_collaboration_collaborators" not in source


def test_factory_fails_closed_for_missing_or_noncallable_core_dependencies() -> None:
    collaborators = _collaborators(document_identity_service=None)
    assert collaborators.document_identity_service is None
    with pytest.raises(TypeError, match="import_document_lock"):
        _collaborators(_import_document_lock=None)
    with pytest.raises(TypeError, match="compatibility_api"):
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
    assert api.calls[0][0] is document_name
    assert api.calls[0][1] is callback


@pytest.mark.parametrize("method", [acquire_document_lock, adopt_dirty_document])
def test_acquisition_and_adoption_reject_unauthenticated_callers(method) -> None:
    lock_module = SimpleNamespace(
        is_enabled=lambda: True,
        get_request_identity=lambda: {"instance_id": "mcp"},
    )
    collaborators = _collaborators(
        _import_document_lock=lambda: lock_module,
    )
    facade = SimpleNamespace(_collaboration_collaborators=collaborators)

    if method is acquire_document_lock:
        result = method(facade, doc_name="Model")
        expected = "LEASE_PROTOCOL_REQUIRED"
    else:
        result = method(facade, selector={"document_name": "Model"})
        expected = "authenticated_session_required"

    assert result["success"] is False
    assert result["error_code"] == expected


def test_snapshot_timeout_cancels_through_the_injected_registry() -> None:
    calls: list[tuple[object, object]] = []
    registry = SimpleNamespace(
        request_cancel=lambda session_id, request_id: (
            calls.append((session_id, request_id))
            or SimpleNamespace(status="requested")
        )
    )
    collaborators = _collaborators(rpc_inflight_request_registry=registry)
    completions: list[tuple[object, object, object]] = []
    facade = SimpleNamespace(
        _collaboration_collaborators=collaborators,
        _complete_request_cancellation=lambda inflight, **kwargs: completions.append(
            (inflight, kwargs.get("dirty"), kwargs.get("snapshot_id"))
        ),
    )
    inflight = SimpleNamespace(session_id="session", request_id="request")
    response = {"success": False, "completion_uncertain": True}

    assert handle_snapshot_timeout(
        facade, response, {"snapshot_id": "snapshot"}, inflight
    ) is response
    assert calls == [("session", "request")]
    assert completions == [(inflight, True, "snapshot")]


def test_cancelled_handoff_continuation_never_consults_claim_authority() -> None:
    continuation = SimpleNamespace(
        state="cancelled",
        error_code=None,
        error=None,
        to_public_dict=lambda: {"state": "cancelled"},
    )
    collaborators = _collaborators(
        rpc_acquisition_claim_store=SimpleNamespace(
            claim=lambda *_args: pytest.fail("claim authority must not be consulted")
        )
    )

    result = claim_handoff_continuation(
        "mcp", "request", continuation, collaborators
    )

    assert result["success"] is False
    assert result["error_code"] == "LOCKED_ERROR_HANDOFF_CANCELLED"


def test_phase12_and_phase13_modules_have_no_runtime_locator() -> None:
    assigned = [OPS / "acquire.py"]
    for pattern in (
        "acquire_v2*.py",
        "acquisition_claims*.py",
        "handoff*.py",
        "reconcile*.py",
    ):
        assigned.extend(OPS.glob(pattern))

    for path in sorted(set(assigned)):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        assert "_rpc_mod" not in source, path.name
        assert not any(
            isinstance(node, ast.ImportFrom)
            and any(alias.name == "_rpc_mod" for alias in node.names)
            for node in ast.walk(tree)
        ), path.name

    phase13_paths = [
        OPS / "release.py",
        OPS / "release_gui.py",
        OPS / "lock_query.py",
        OPS / "lock_query_helpers.py",
        *OPS.glob("save*.py"),
    ]
    for path in sorted(set(phase13_paths)):
        assert "_rpc_mod" not in path.read_text(encoding="utf-8"), path.name
