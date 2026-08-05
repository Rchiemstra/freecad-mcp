"""Focused RPC tests for initial dirty-document lease adoption."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.document_lease import (
    AuthorizationError,
    DocumentIdentityService,
    DocumentLeaseService,
    LeaseConflictError,
    LeaseOwner,
    LeaseState,
    LocalRuntimeIdentity,
    ProcessLivenessEvidence,
    SidecarCommitUncertainError,
    SidecarStore,
    capture_file_baseline,
    sidecar_path_for,
)
from addon.FreeCADMCP.document_lease import observer as lease_observer
from addon.FreeCADMCP.rpc_server import rpc_server
from addon.FreeCADMCP.rpc_server import snapshot_service
from addon.FreeCADMCP.rpc_server.acquisition_claims import AcquisitionClaimStore
from addon.FreeCADMCP.rpc_server.handoff_continuations import (
    HandoffContinuationStore,
)
from addon.FreeCADMCP.rpc_server.inflight_requests import InflightRequestRegistry
from addon.FreeCADMCP.rpc_server.lease_protocol import RequestReplayCache

pytestmark = pytest.mark.unit


class _DirtyDocument:
    def __init__(self, path):
        self.Name = "DirtyModel"
        self.Label = "Dirty model"
        self.FileName = str(path)
        self.Modified = True
        self._core_generation = 0
        self._core_owner = "unrestricted"
        self._core_provider = ""
        self._core_restricted = False
        self._save_as_capability = False
        self.capability_calls = []
        self.owner_calls = []
        self.fail_snapshot = False
        self.misreport_provider_for = None

    def mutationAuthorityStatus(self):
        return {
            "owner": self._core_owner,
            "generation": self._core_generation,
            "provider_id": (
                "misreported-provider"
                if self._core_provider == self.misreport_provider_for
                else self._core_provider
            ),
            "restricted": self._core_restricted,
        }

    def openMutationCapability(self, kinds=None, generation=0):
        requested_generation = int(generation)
        if (
            not self._core_restricted
            or requested_generation not in {0, self._core_generation}
            or tuple(kinds or ()) != ("SaveAs",)
        ):
            raise RuntimeError("wrong owner, generation, or mutation kind")
        self.capability_calls.append((tuple(kinds or ()), requested_generation))
        self._save_as_capability = True
        return object()

    def setMutationOwner(self, mode, generation=0, provider_id=""):
        self.owner_calls.append((mode, int(generation), provider_id))
        self._core_owner = mode
        self._core_provider = provider_id
        self._core_restricted = mode == "mcp"
        self._core_generation = int(generation)

    def saveCopy(self, path):
        if self._core_restricted and not self._save_as_capability:
            raise RuntimeError("SaveAs denied by core mutation authority")
        self._save_as_capability = False
        if self.fail_snapshot:
            raise RuntimeError("injected recovery snapshot failure")
        Path(path).write_bytes(b"PK\x03\x04" + b"snapshot" * 4)


class _DocumentLock:
    request_id = "dirty-adoption-request"

    @staticmethod
    def is_enabled():
        return True

    @staticmethod
    def get_request_identity():
        return {
            "request_id": _DocumentLock.request_id,
            "authenticated_session_id": "rpc-session",
            "instance_id": "11111111-1111-4111-8111-111111111111",
            "pid": 101,
            "mcp_process_started_at": "2026-07-28T00:00:01Z",
            "host": rpc_server.platform.node(),
            "client": "pytest",
            "agent_id": "agent-a",
        }

    @staticmethod
    def begin_agent_mutation_scope(_request_id, _document_keys):
        return True

    @staticmethod
    def end_agent_mutation_scope(_request_id, _document_keys):
        return True


class _LegacyGlobalFixtureRPC(rpc_server.FreeCADRPC):
    """Keep older behavior fixtures independent from production graph assembly."""

    @property
    def _collaboration_collaborators(self):
        return rpc_server._build_collaboration_collaborators()

    @property
    def _execution_collaborators(self):
        return rpc_server._build_execution_collaborators(
            compatibility_api=self._collaboration_collaborators.compatibility_api
        )


def _configure_dirty_adoption(monkeypatch, tmp_path):
    model = tmp_path / "DirtyModel.FCStd"
    original = b"existing saved baseline"
    model.write_bytes(original)
    document = _DirtyDocument(model)
    identities = DocumentIdentityService()
    runtime = SimpleNamespace(
        profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=42,
        freecad_process_started_at="2026-07-28T00:00:00Z",
        boot_id="test-boot",
    )
    service = DocumentLeaseService(
        identities,
        SidecarStore(network_detector=lambda _path: False),
        local_runtime_identity=LocalRuntimeIdentity(
            addon_profile_id=runtime.profile_id,
            addon_runtime_id=runtime.addon_runtime_id,
            freecad_pid=runtime.freecad_pid,
            freecad_process_started_at=runtime.freecad_process_started_at,
            boot_id=runtime.boot_id,
            hostname=rpc_server.platform.node(),
        ),
    )
    _DocumentLock.request_id = str(uuid.uuid4())
    monkeypatch.setattr(
        rpc_server, "rpc_acquisition_claim_store", AcquisitionClaimStore()
    )
    monkeypatch.setattr(
        rpc_server, "rpc_handoff_continuation_store", HandoffContinuationStore()
    )
    monkeypatch.setattr(
        rpc_server, "rpc_inflight_request_registry", InflightRequestRegistry()
    )
    monkeypatch.setattr(
        rpc_server, "rpc_request_replay_cache", RequestReplayCache()
    )
    monkeypatch.setattr(rpc_server, "_import_document_lock", lambda: _DocumentLock())
    monkeypatch.setattr(rpc_server, "document_identity_service", identities)
    monkeypatch.setattr(rpc_server, "document_lease_service", service)
    monkeypatch.setattr(rpc_server, "rpc_runtime_manifest", runtime)
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "getDocument",
        lambda name: document if name == document.Name else None,
    )
    monkeypatch.setattr(
        rpc_server.FreeCAD, "listDocuments", lambda: {document.Name: document}
    )
    rpc = _LegacyGlobalFixtureRPC()
    monkeypatch.setattr(
        rpc, "_dispatch_gui", lambda task, timeout=None, **_kwargs: task()
    )
    return rpc, document, model, original, service


def _seed_dead_local_owner(document, service, *, mcp_hostname=None):
    identity = service.identity_service.register_document(document)
    runtime = rpc_server.rpc_runtime_manifest
    abandoned_owner = LeaseOwner(
        addon_profile_id=runtime.profile_id,
        addon_runtime_id=runtime.addon_runtime_id,
        freecad_pid=runtime.freecad_pid,
        freecad_process_started_at=runtime.freecad_process_started_at,
        boot_id=runtime.boot_id,
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=202,
        mcp_process_started_at="2026-07-28T00:00:00Z",
        hostname=rpc_server.platform.node(),
        mcp_hostname=(
            rpc_server.platform.node()
            if mcp_hostname is None
            else mcp_hostname
        ),
        client="exited-mcp",
        agent_id="",
    )
    abandoned = service.acquire(
        identity.session_uuid,
        abandoned_owner,
        snapshot_id=str(uuid.uuid4()),
    )
    service._process_liveness_probe = (
        lambda pid: ProcessLivenessEvidence(exists=False)
        if pid == abandoned_owner.mcp_pid
        else ProcessLivenessEvidence(exists=None)
    )
    document.setMutationOwner(
        "mcp",
        abandoned.record.generation,
        abandoned_owner.mcp_instance_id,
    )
    return identity, abandoned_owner, abandoned


def test_dirty_adoption_rejects_when_confirmation_hook_returns_false(
    tmp_path, monkeypatch
):
    """RPC still honors a False confirmation hook (defensive reject path)."""

    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        rpc_server, "_confirm_dirty_document_adoption_gui", lambda *_args: False
    )

    result = rpc.adopt_dirty_document(selector={"document_name": document.Name})

    assert result["success"] is False
    assert result["error_code"] == "DIRTY_ADOPTION_PRECONDITION_FAILED"
    assert service.list_records() == []
    assert not sidecar_path_for(model).exists()
    assert model.read_bytes() == original
    assert document.Modified is True


def test_dirty_adoption_rejects_unsupported_selector_fields_before_confirmation(
    tmp_path, monkeypatch
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    confirmations = []
    monkeypatch.setattr(
        rpc_server,
        "_confirm_dirty_document_adoption_gui",
        lambda *_args: confirmations.append(True) or True,
    )

    result = rpc.adopt_dirty_document(selector={"doc_name": document.Name})

    assert result["success"] is False
    assert "Unsupported DocumentSelector field(s): doc_name" in result["error"]
    assert "document_name, document_session_uuid, and canonical_path" in result["error"]
    assert confirmations == []
    assert service.list_records() == []
    assert not sidecar_path_for(model).exists()
    assert model.read_bytes() == original
    assert document.Modified is True


def test_dirty_adoption_snapshots_then_returns_dirty_lease(tmp_path, monkeypatch):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    confirmations = []
    snapshots = []
    snapshot_id = str(uuid.uuid4())
    monkeypatch.setattr(
        rpc_server,
        "_confirm_dirty_document_adoption_gui",
        lambda doc, identity: confirmations.append((doc, identity)) or True,
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda doc: snapshots.append(doc) or snapshot_id,
    )

    result = rpc.adopt_dirty_document(
        selector={"document_name": document.Name},
        task_description="Repair pre-existing unsaved state",
        agent_id="agent-a",
    )

    assert result["success"] is True
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["document_state"]["dirty"] is True
    assert result["document_state"]["last_mutation_revision"] == 1
    assert result["document_state"]["snapshot_id"] == snapshot_id
    assert result["credential"]["token"]
    assert confirmations and confirmations[0][0] is document
    assert snapshots == [document]
    assert service.list_records()[0]["document_state"]["dirty"] is True
    assert sidecar_path_for(model).exists()
    assert model.read_bytes() == original
    assert document.Modified is True


def test_clean_acquisition_self_heals_dead_mcp_owner_in_same_addon(
    tmp_path,
    monkeypatch,
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    document.Modified = False
    _identity, abandoned_owner, abandoned = _seed_dead_local_owner(
        document, service
    )
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    monkeypatch.setattr(snapshot_service, "_recovery_root", lambda: recovery)

    result = rpc.acquire_document_lock(
        selector={"document_name": document.Name},
        task_description="Continue after the previous MCP exited",
    )

    assert result["success"] is True, result
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["credential"]["generation"] == abandoned.record.generation + 1
    assert result["owner"]["mcp_instance_id"] == (
        _DocumentLock.get_request_identity()["instance_id"]
    )
    new_snapshot = result["document_state"]["snapshot_id"]
    assert (recovery / f"{new_snapshot}.FCStd").is_file()
    assert document.capability_calls == [(("SaveAs",), 0)]
    assert document.owner_calls[-1][1] == abandoned.record.generation + 1
    with pytest.raises(AuthorizationError):
        service.authorize(abandoned.credential)
    assert model.read_bytes() == original
    assert document.Modified is False


def test_local_orphan_cancel_before_irreversible_handoff_preserves_old_authority(
    tmp_path,
    monkeypatch,
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    document.Modified = False
    identity, abandoned_owner, abandoned = _seed_dead_local_owner(
        document,
        service,
    )
    sidecar = sidecar_path_for(model)
    before = sidecar.read_bytes()
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    monkeypatch.setattr(snapshot_service, "_recovery_root", lambda: recovery)
    registry = InflightRequestRegistry()
    inflight = registry.register(
        "rpc-session",
        _DocumentLock.request_id,
        "acquire_document_lock",
        lease_affecting=True,
    )
    monkeypatch.setattr(rpc_server, "rpc_inflight_request_registry", registry)
    original_status = document.mutationAuthorityStatus
    status_calls = []

    def cancel_at_post_snapshot_status():
        status_calls.append(True)
        if len(status_calls) == 3:
            assert inflight.token.request_cancel()[0] is True
        return original_status()

    document.mutationAuthorityStatus = cancel_at_post_snapshot_status
    rpc._inflight_context.value = inflight
    try:
        with pytest.raises(Exception) as failure:
            rpc.acquire_document_lock(
                selector={"document_name": document.Name},
                task_description="Cancel just before orphan authority rotation",
            )
    finally:
        del rpc._inflight_context.value

    assert failure.value.__class__.__name__ == "RequestCancellationError"
    assert len(status_calls) == 3
    assert sidecar.read_bytes() == before
    assert service.authorize(abandoned.credential).lease_id == (
        abandoned.record.lease_id
    )
    assert document.mutationAuthorityStatus() == {
        "owner": "mcp",
        "generation": abandoned.record.generation,
        "provider_id": abandoned_owner.mcp_instance_id,
        "restricted": True,
    }
    assert list(recovery.iterdir()) == []
    assert model.read_bytes() == original


def test_local_orphan_cancel_after_irreversible_boundary_cannot_hide_credential(
    tmp_path,
    monkeypatch,
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    document.Modified = False
    _identity, _abandoned_owner, abandoned = _seed_dead_local_owner(
        document,
        service,
    )
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    monkeypatch.setattr(snapshot_service, "_recovery_root", lambda: recovery)
    registry = InflightRequestRegistry()
    inflight = registry.register(
        "rpc-session",
        _DocumentLock.request_id,
        "acquire_document_lock",
        lease_affecting=True,
    )
    monkeypatch.setattr(rpc_server, "rpc_inflight_request_registry", registry)
    original_recover = service.recover_orphaned_local_mcp_acquisition
    cancel_attempts = []

    def attempt_late_cancel(*args, **kwargs):
        cancel_attempts.append(inflight.token.request_cancel())
        return original_recover(*args, **kwargs)

    monkeypatch.setattr(
        service,
        "recover_orphaned_local_mcp_acquisition",
        attempt_late_cancel,
    )
    rpc._inflight_context.value = inflight
    try:
        result = rpc.acquire_document_lock(
            selector={"document_name": document.Name},
            task_description="Finish after crossing the authority boundary",
        )
    finally:
        del rpc._inflight_context.value

    assert result["success"] is True, result
    assert result["credential"]["token"]
    assert cancel_attempts and cancel_attempts[0][0] is False
    assert cancel_attempts[0][1].cancellation_requested is False
    assert inflight.token.snapshot().phase == "local_orphan_authority_handoff"
    assert rpc_server.rpc_acquisition_claim_store.claimable(
        _DocumentLock.get_request_identity()["instance_id"],
        _DocumentLock.request_id,
    )
    assert result["credential"]["generation"] == abandoned.record.generation + 1
    assert model.read_bytes() == original


def test_local_orphan_timeout_after_handoff_keeps_claimable_credential(
    tmp_path,
    monkeypatch,
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    document.Modified = False
    _identity, _abandoned_owner, abandoned = _seed_dead_local_owner(
        document,
        service,
    )
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    monkeypatch.setattr(snapshot_service, "_recovery_root", lambda: recovery)
    registry = InflightRequestRegistry()
    inflight = registry.register(
        "rpc-session",
        _DocumentLock.request_id,
        "acquire_document_lock",
        lease_affecting=True,
    )
    claims = AcquisitionClaimStore()
    monkeypatch.setattr(rpc_server, "rpc_inflight_request_registry", registry)
    monkeypatch.setattr(rpc_server, "rpc_acquisition_claim_store", claims)
    dispatch_count = []

    def report_timeout_after_task_completed(task, timeout=None, **_kwargs):
        del timeout
        dispatch_count.append(True)
        value = task()
        if len(dispatch_count) == 2:
            assert value["success"] is True
            return {
                "success": False,
                "completion_uncertain": True,
                "request_id": _DocumentLock.request_id,
            }
        return value

    monkeypatch.setattr(rpc, "_dispatch_gui", report_timeout_after_task_completed)
    rpc._inflight_context.value = inflight
    try:
        result = rpc.acquire_document_lock(
            selector={"document_name": document.Name},
            task_description="Simulate a lost post-handoff GUI response",
        )
    finally:
        del rpc._inflight_context.value

    assert result["completion_uncertain"] is True
    runtime_id = _DocumentLock.get_request_identity()["instance_id"]
    assert claims.claimable(runtime_id, _DocumentLock.request_id)
    claimed = claims.claim(runtime_id, _DocumentLock.request_id)
    assert claimed["success"] is True
    assert claimed["credential"]["token"]
    assert claimed["credential"]["generation"] == abandoned.record.generation + 1
    assert inflight.token.snapshot().cancellation_requested is False
    assert service.list_records()[0]["owner"]["mcp_instance_id"] == runtime_id
    assert model.read_bytes() == original


def test_local_orphan_unreadable_post_publish_commit_returns_escrowed_warning(
    tmp_path,
    monkeypatch,
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    document.Modified = False
    _identity, _abandoned_owner, abandoned = _seed_dead_local_owner(
        document,
        service,
    )
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    monkeypatch.setattr(snapshot_service, "_recovery_root", lambda: recovery)
    real_replace = service.sidecar_store.replace
    injected = {"done": False}

    def publish_then_make_reread_unavailable(path, record, *, expected):
        real_replace(path, record, expected=expected)
        if not injected["done"]:
            injected["done"] = True
            raise SidecarCommitUncertainError(
                "simulated unavailable guarded reread",
                persisted=None,
            )

    monkeypatch.setattr(
        service.sidecar_store,
        "replace",
        publish_then_make_reread_unavailable,
    )
    result = rpc.acquire_document_lock(
        selector={"document_name": document.Name},
        task_description="Complete an uncertain published orphan handoff",
    )

    runtime_id = _DocumentLock.get_request_identity()["instance_id"]
    assert result["success"] is True
    assert result["coordination_uncertain"] is True
    assert result["warning_code"] == "SIDECAR_COMMIT_UNCERTAIN"
    assert result["credential"]["generation"] == abandoned.record.generation + 1
    assert rpc_server.rpc_acquisition_claim_store.claimable(
        runtime_id,
        _DocumentLock.request_id,
    )
    claimed = rpc_server.rpc_acquisition_claim_store.claim(
        runtime_id,
        _DocumentLock.request_id,
    )
    assert claimed["credential"]["token"] == result["credential"]["token"]
    assert service.list_records()[0]["owner"]["mcp_instance_id"] == runtime_id
    assert model.read_bytes() == original


def test_clean_acquisition_repairs_legacy_worker_save_intervention(
    tmp_path,
    monkeypatch,
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    document.Modified = False
    identity, abandoned_owner, abandoned = _seed_dead_local_owner(
        document,
        service,
        mcp_hostname="",
    )
    intervened = service.takeover(
        identity.session_uuid,
        dirty=True,
        reason=(
            "Unscoped FreeCAD save detected: "
            "freecad_mcp_workers/snapshots/0001_DirtyModel.FCStd"
        ),
    )
    document._core_owner = "user"
    document._core_provider = abandoned_owner.mcp_instance_id
    document._core_restricted = False
    document._core_generation = intervened.generation
    service._process_liveness_probe = lambda _pid: pytest.fail(
        "the already-revoked legacy credential needs no PID probe"
    )
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    monkeypatch.setattr(snapshot_service, "_recovery_root", lambda: recovery)

    result = rpc.acquire_document_lock(
        selector={"document_name": document.Name},
        task_description="Recover the misattributed worker snapshot",
    )

    assert result["success"] is True, result
    assert result["credential"]["generation"] == intervened.generation + 1
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["document_state"]["dirty"] is False
    assert result["document_state"]["user_intervened"] is False
    assert result["owner"]["mcp_hostname"] == rpc_server.platform.node()
    assert document.capability_calls == []
    with pytest.raises(AuthorizationError):
        service.authorize(abandoned.credential)
    assert model.read_bytes() == original
    assert document.Modified is False


def test_legacy_recovery_rolls_back_sidecar_and_user_core_on_sync_mismatch(
    tmp_path,
    monkeypatch,
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    document.Modified = False
    identity, abandoned_owner, abandoned = _seed_dead_local_owner(
        document,
        service,
        mcp_hostname="",
    )
    intervened = service.takeover(
        identity.session_uuid,
        dirty=True,
        reason=(
            "Unscoped FreeCAD save detected: "
            "freecad_mcp_workers/snapshots/0001_DirtyModel.FCStd"
        ),
    )
    document._core_owner = "user"
    document._core_provider = abandoned_owner.mcp_instance_id
    document._core_restricted = False
    document._core_generation = intervened.generation
    document.misreport_provider_for = (
        _DocumentLock.get_request_identity()["instance_id"]
    )
    service._process_liveness_probe = lambda _pid: pytest.fail(
        "the already-revoked legacy credential needs no PID probe"
    )
    sidecar = sidecar_path_for(model)
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    monkeypatch.setattr(snapshot_service, "_recovery_root", lambda: recovery)

    result = rpc.acquire_document_lock(
        selector={"document_name": document.Name},
        task_description="Retry a mismatched core handoff",
    )

    assert result["success"] is False
    assert result["error_code"] == "LEASE_COORDINATION_LOST"
    assert "core mutation authority handoff failed" in result["error"]
    persisted = service.sidecar_store.read(sidecar)
    assert persisted.lease_id == intervened.lease_id
    assert persisted.generation == intervened.generation
    assert persisted.token_fingerprint == intervened.token_fingerprint
    assert persisted.owner == intervened.owner
    assert persisted.state == LeaseState.USER_INTERVENED
    assert persisted.record_revision == intervened.record_revision + 2
    assert persisted.state_revision == intervened.state_revision + 2
    assert service.get(identity.session_uuid)["lease"]["state"] == (
        LeaseState.USER_INTERVENED.value
    )
    assert document.mutationAuthorityStatus() == {
        "owner": "user",
        "generation": intervened.generation,
        "provider_id": abandoned_owner.mcp_instance_id,
        "restricted": False,
    }
    assert list(recovery.iterdir()) == []
    with pytest.raises(AuthorizationError):
        service.authorize(abandoned.credential)
    assert model.read_bytes() == original
    assert document.Modified is False


def test_local_orphan_snapshot_failure_preserves_old_sidecar_and_core_fence(
    tmp_path,
    monkeypatch,
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    document.Modified = False
    identity, abandoned_owner, abandoned = _seed_dead_local_owner(
        document, service
    )
    sidecar = sidecar_path_for(model)
    before = sidecar.read_bytes()
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    monkeypatch.setattr(snapshot_service, "_recovery_root", lambda: recovery)
    document.fail_snapshot = True

    result = rpc.acquire_document_lock(
        selector={"document_name": document.Name},
        task_description="Retry after the previous MCP exited",
    )

    assert result["success"] is False
    assert "injected recovery snapshot failure" in result["error"]
    assert sidecar.read_bytes() == before
    assert service.get(identity.session_uuid)["lease"]["state"] == (
        LeaseState.LOCKED_IDLE.value
    )
    assert service.authorize(abandoned.credential).generation == (
        abandoned.record.generation
    )
    assert document.mutationAuthorityStatus() == {
        "owner": "mcp",
        "generation": abandoned.record.generation,
        "provider_id": abandoned_owner.mcp_instance_id,
        "restricted": True,
    }
    assert document.capability_calls == [(("SaveAs",), 0)]
    assert list(recovery.iterdir()) == []
    assert model.read_bytes() == original


def test_automatic_dirty_adoption_handoffs_local_locked_error(
    tmp_path,
    monkeypatch,
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    _identity, baseline, snapshot_id, active, errored = _seed_locked_error_for_handoff(
        service, document, model
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document: pytest.fail("handoff must preserve the existing snapshot"),
    )

    def sync_start(**kwargs):
        rpc_server.rpc_handoff_continuation_store.begin(
            mcp_runtime_id=kwargs["mcp_runtime_id"],
            request_id=kwargs["request_id"],
        )
        rpc._run_locked_error_handoff_continuation(**kwargs)

    monkeypatch.setattr(rpc, "_start_locked_error_handoff_continuation", sync_start)

    pending = rpc.adopt_dirty_document(
        selector={"document_name": document.Name},
        task_description="Continue after typed operation rollback",
    )

    assert pending["success"] is False
    assert pending["error_code"] == "LOCKED_ERROR_HANDOFF_PENDING"
    assert pending["confirmation_pending"] is False
    runtime_id = _DocumentLock.get_request_identity()["instance_id"]
    continuation = _await_handoff_claimable(runtime_id, pending["request_id"])
    assert continuation is not None and continuation.state == "claimable"
    result = rpc.claim_acquisition_result(pending["request_id"])

    assert result["success"] is True, result
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["document_state"]["dirty"] is True
    assert result["document_state"]["snapshot_id"] == snapshot_id
    assert result["document_state"]["baseline"] == baseline.to_dict()
    assert result["credential"]["generation"] == errored.generation + 1
    assert result["owner"]["mcp_instance_id"] == _DocumentLock.get_request_identity()[
        "instance_id"
    ]
    with pytest.raises(AuthorizationError):
        service.authorize(active.credential)
    persisted = service.sidecar_store.read(sidecar_path_for(model))
    assert persisted.generation == result["credential"]["generation"]
    assert persisted.state == LeaseState.LOCKED_IDLE
    assert persisted.snapshot_id == snapshot_id
    assert model.read_bytes() == original
    assert document.Modified is True


def test_locked_error_handoff_defensive_authorization_rejection(
    tmp_path, monkeypatch
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    identity, _baseline, _snapshot_id, active, _errored = _seed_locked_error_for_handoff(
        service, document, model
    )
    monkeypatch.setattr(
        rpc_server, "_authorize_locked_error_handoff_gui", lambda *_args: False
    )

    def sync_start(**kwargs):
        rpc_server.rpc_handoff_continuation_store.begin(
            mcp_runtime_id=kwargs["mcp_runtime_id"],
            request_id=kwargs["request_id"],
        )
        rpc._run_locked_error_handoff_continuation(**kwargs)

    monkeypatch.setattr(rpc, "_start_locked_error_handoff_continuation", sync_start)

    pending = rpc.adopt_dirty_document(selector={"document_name": document.Name})

    assert pending["success"] is False
    assert pending["error_code"] == "LOCKED_ERROR_HANDOFF_PENDING"
    runtime_id = _DocumentLock.get_request_identity()["instance_id"]
    continuation = _await_handoff_claimable(runtime_id, pending["request_id"])
    assert continuation is not None
    assert continuation.state == "denied"
    assert "handoff" in str(continuation.error or "").lower()
    assert service.get(identity.session_uuid)["lease"]["state"] == (
        LeaseState.LOCKED_ERROR.value
    )
    assert model.read_bytes() == original


def test_locked_error_handoff_pending_returns_before_authorization(
    tmp_path, monkeypatch
):
    """Detect returns immediately while automatic bounded handoff runs."""

    import threading
    import time

    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    _identity, _baseline, snapshot_id, active, errored = _seed_locked_error_for_handoff(
        service, document, model
    )
    release_authorize = threading.Event()
    submit_timeouts = []

    class _Dispatcher:
        def submit(self, task, timeout, **_kwargs):
            name = getattr(task, "__name__", "")
            submit_timeouts.append((name, timeout))
            return task()

    def gated_authorize(_document, _identity):
        assert release_authorize.wait(timeout=5)
        return True

    monkeypatch.setattr(rpc_server, "gui_dispatcher", _Dispatcher())
    monkeypatch.setattr(
        rpc,
        "_dispatch_gui",
        rpc_server.FreeCADRPC._dispatch_gui.__get__(rpc, rpc_server.FreeCADRPC),
    )
    monkeypatch.setattr(
        rpc_server, "_authorize_locked_error_handoff_gui", gated_authorize
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document: pytest.fail("handoff must preserve the existing snapshot"),
    )

    started = time.monotonic()
    pending = rpc.adopt_dirty_document(selector={"document_name": document.Name})
    detect_elapsed = time.monotonic() - started

    assert pending["success"] is False
    assert pending["error_code"] == "LOCKED_ERROR_HANDOFF_PENDING"
    assert pending["request_id"]
    # Must beat any client lifecycle socket (150s) by a wide margin.
    assert detect_elapsed < 2.0
    assert any(
        name == "reserve_gui" and timeout == rpc.ACQUIRE_GUI_PHASE_TIMEOUT_S
        for name, timeout in submit_timeouts
    )
    runtime_id = _DocumentLock.get_request_identity()["instance_id"]
    mid = rpc_server.rpc_handoff_continuation_store.get(
        runtime_id, pending["request_id"]
    )
    assert mid is not None
    assert mid.state in {"pending_authorization", "authorizing"}
    assert not rpc_server.rpc_acquisition_claim_store.claimable(
        runtime_id, pending["request_id"]
    )

    release_authorize.set()
    continuation = _await_handoff_claimable(runtime_id, pending["request_id"])
    assert continuation is not None and continuation.state == "claimable"
    assert (
        "authorize_handoff_gui",
        rpc.ACQUIRE_GUI_PHASE_TIMEOUT_S,
    ) in submit_timeouts
    result = rpc.claim_acquisition_result(pending["request_id"])

    assert result["success"] is True, result
    assert result["credential"]["generation"] == errored.generation + 1
    assert result["document_state"]["snapshot_id"] == snapshot_id
    with pytest.raises(AuthorizationError):
        service.authorize(active.credential)
    assert model.read_bytes() == original


def test_locked_error_handoff_claim_timeout_still_escrows_late_cas(
    tmp_path, monkeypatch
):
    """Claim-phase waiter timeout must not fail over a late successful CAS."""

    import threading
    import time

    from addon.FreeCADMCP.rpc_server.gui_dispatcher import GuiOutcome

    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    _identity, _baseline, snapshot_id, active, errored = _seed_locked_error_for_handoff(
        service, document, model
    )
    monkeypatch.setattr(rpc, "ACQUIRE_GUI_PHASE_TIMEOUT_S", 0.05)
    real_claim = service.claim_locked_error_handoff

    def slow_claim(*args, **kwargs):
        grant = real_claim(*args, **kwargs)
        time.sleep(0.25)
        return grant

    monkeypatch.setattr(service, "claim_locked_error_handoff", slow_claim)

    class _TimeoutAwareDispatcher:
        def submit(self, task, timeout, **kwargs):
            on_complete = kwargs.get("on_complete")
            if timeout is None:
                value = task()
                if on_complete is not None:
                    on_complete("test", GuiOutcome(True, value=value))
                return value
            box: dict = {}
            done = threading.Event()

            def runner():
                try:
                    box["value"] = task()
                    box["ok"] = True
                except Exception as exc:
                    box["error"] = str(exc)
                    box["ok"] = False
                finally:
                    done.set()
                    if on_complete is not None:
                        if box.get("ok"):
                            on_complete(
                                "test", GuiOutcome(True, value=box["value"])
                            )
                        else:
                            on_complete(
                                "test",
                                GuiOutcome(False, error=box.get("error")),
                            )

            threading.Thread(target=runner, daemon=True).start()
            if done.wait(timeout=float(timeout)):
                if box.get("ok"):
                    return box["value"]
                return {
                    "success": False,
                    "error_code": "LEASE_CONFLICT",
                    "error": box.get("error") or "claim failed",
                }
            return {
                "success": False,
                "error_code": "GUI_TIMEOUT_DURING_EXECUTION",
                "error": "GUI dispatch timed out during execution",
                "completion_uncertain": True,
                "execution_started": True,
            }

    monkeypatch.setattr(rpc_server, "gui_dispatcher", _TimeoutAwareDispatcher())
    monkeypatch.setattr(
        rpc,
        "_dispatch_gui",
        rpc_server.FreeCADRPC._dispatch_gui.__get__(rpc, rpc_server.FreeCADRPC),
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document: pytest.fail("handoff must preserve the existing snapshot"),
    )

    pending = rpc.adopt_dirty_document(selector={"document_name": document.Name})
    assert pending["error_code"] == "LOCKED_ERROR_HANDOFF_PENDING"
    runtime_id = _DocumentLock.get_request_identity()["instance_id"]

    # First observation may be uncertain; late escrow must still land.
    deadline = time.monotonic() + 5.0
    saw_uncertain = False
    while time.monotonic() < deadline:
        continuation = rpc_server.rpc_handoff_continuation_store.get(
            runtime_id, pending["request_id"]
        )
        if continuation is not None and continuation.state == "claiming_uncertain":
            saw_uncertain = True
        if (
            continuation is not None
            and continuation.state == "claimable"
        ) or rpc_server.rpc_acquisition_claim_store.claimable(
            runtime_id, pending["request_id"]
        ):
            break
        time.sleep(0.02)
    continuation = _await_handoff_claimable(runtime_id, pending["request_id"])
    assert continuation is not None and continuation.state == "claimable"
    assert saw_uncertain or rpc_server.rpc_acquisition_claim_store.claimable(
        runtime_id, pending["request_id"]
    )
    result = rpc.claim_acquisition_result(pending["request_id"])
    assert result["success"] is True, result
    assert result["credential"]["generation"] == errored.generation + 1
    assert result["document_state"]["snapshot_id"] == snapshot_id
    with pytest.raises(AuthorizationError):
        service.authorize(active.credential)
    assert model.read_bytes() == original


def test_locked_error_handoff_cancel_before_cas_keeps_prior_owner(
    tmp_path, monkeypatch
):
    """cancel_request before CAS must ignore a later FreeCAD Yes."""

    import threading
    import time

    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    identity, _baseline, _snapshot_id, active, _errored = _seed_locked_error_for_handoff(
        service, document, model
    )
    release_authorize = threading.Event()

    class _Dispatcher:
        def submit(self, task, timeout, **_kwargs):
            return task()

    def gated_authorize(_document, _identity):
        assert release_authorize.wait(timeout=5)
        return True

    monkeypatch.setattr(rpc_server, "gui_dispatcher", _Dispatcher())
    monkeypatch.setattr(
        rpc,
        "_dispatch_gui",
        rpc_server.FreeCADRPC._dispatch_gui.__get__(rpc, rpc_server.FreeCADRPC),
    )
    monkeypatch.setattr(
        rpc_server, "_authorize_locked_error_handoff_gui", gated_authorize
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document: pytest.fail("cancelled handoff must not snapshot"),
    )

    pending = rpc.adopt_dirty_document(selector={"document_name": document.Name})
    assert pending["error_code"] == "LOCKED_ERROR_HANDOFF_PENDING"
    runtime_id = _DocumentLock.get_request_identity()["instance_id"]

    # Let the continuation enter automatic authorization before cancel.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        mid = rpc_server.rpc_handoff_continuation_store.get(
            runtime_id, pending["request_id"]
        )
        if mid is not None and mid.state in {
            "pending_authorization",
            "authorizing",
        }:
            break
        time.sleep(0.01)

    cancelled = rpc.cancel_request(pending["request_id"])
    assert cancelled["success"] is True, cancelled
    assert cancelled.get("handoff_cancelled") is True

    release_authorize.set()
    continuation = _await_handoff_claimable(runtime_id, pending["request_id"])
    assert continuation is not None
    assert continuation.state == "cancelled"
    assert not rpc_server.rpc_acquisition_claim_store.claimable(
        runtime_id, pending["request_id"]
    )
    status = rpc.get_request_status(pending["request_id"])
    assert status["state"] == "cancelled"
    assert status["handoff_pending"] is False
    # Prior LOCKED_ERROR credential must still authorize.
    service.authorize(
        active.credential,
        selector={"document_session_uuid": identity.session_uuid},
        allowed_states={LeaseState.LOCKED_ERROR},
    )
    assert service.get(identity.session_uuid)["lease"]["state"] == (
        LeaseState.LOCKED_ERROR.value
    )
    assert model.read_bytes() == original


def _seed_locked_error_for_handoff(service, document, model):
    identity = service.identity_service.register_document(document)
    runtime = service.local_runtime_identity
    old_owner = LeaseOwner(
        addon_profile_id=runtime.addon_profile_id,
        addon_runtime_id=runtime.addon_runtime_id,
        freecad_pid=runtime.freecad_pid,
        freecad_process_started_at=runtime.freecad_process_started_at,
        boot_id=runtime.boot_id,
        mcp_instance_id="22222222-2222-4222-8222-222222222222",
        mcp_pid=202,
        mcp_process_started_at="2026-07-28T00:00:02Z",
        hostname=runtime.hostname,
        client="previous-agent",
        agent_id="previous-agent",
    )
    baseline = capture_file_baseline(
        model,
        platform=service.identity_service.platform,
    )
    snapshot_id = str(uuid.uuid4())
    reservation = service.begin_dirty_adoption(
        identity.session_uuid,
        old_owner,
        document_dirty=True,
        local_confirmation=True,
    )
    service.record_acquisition_snapshot(
        reservation.credential,
        snapshot_id=snapshot_id,
    )
    active = service.complete_dirty_adoption(
        reservation.credential,
        baseline=baseline,
        baseline_validated=True,
        snapshot_id=snapshot_id,
    )
    service.begin_mutation(active.credential, operation="pad_feature")
    errored = service.record_error(
        active.credential,
        code="OPERATION_FAILED",
        message="SILENT BUILD MISMATCH",
        dirty=True,
    )
    return identity, baseline, snapshot_id, active, errored


def _await_handoff_claimable(mcp_runtime_id, request_id, *, timeout_s=5.0):
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        continuation = rpc_server.rpc_handoff_continuation_store.get(
            mcp_runtime_id, request_id
        )
        if continuation is not None and continuation.state in {
            "claimable",
            "denied",
            "failed",
            "cancelled",
        }:
            return continuation
        if (
            rpc_server.rpc_acquisition_claim_store is not None
            and rpc_server.rpc_acquisition_claim_store.claimable(
                mcp_runtime_id, request_id
            )
        ):
            return continuation
        time.sleep(0.02)
    return rpc_server.rpc_handoff_continuation_store.get(mcp_runtime_id, request_id)


def test_dirty_adoption_retries_unreturned_stale_reservation(tmp_path, monkeypatch):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    runtime = service.local_runtime_identity
    identity = service.identity_service.register_document(document)
    abandoned = service.begin_dirty_adoption(
        identity.session_uuid,
        LeaseOwner(
            addon_profile_id=runtime.addon_profile_id,
            addon_runtime_id=runtime.addon_runtime_id,
            freecad_pid=runtime.freecad_pid,
            freecad_process_started_at=runtime.freecad_process_started_at,
            boot_id=runtime.boot_id,
            mcp_instance_id="22222222-2222-4222-8222-222222222222",
            mcp_pid=202,
            mcp_process_started_at="2026-07-28T00:00:02Z",
            hostname=runtime.hostname,
            client="pytest",
            agent_id="abandoned-agent",
        ),
        document_dirty=True,
        local_confirmation=True,
    )
    service.mark_stale(abandoned.credential.document_session_uuid)
    snapshot_id = str(uuid.uuid4())
    monkeypatch.setattr(
        rpc_server, "_confirm_dirty_document_adoption_gui", lambda *_args: True
    )
    monkeypatch.setattr(
        rpc_server, "create_lease_baseline_snapshot_gui", lambda _doc: snapshot_id
    )

    result = rpc.adopt_dirty_document(selector={"document_name": document.Name})

    assert result["success"] is True, result
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["credential"]["generation"] == abandoned.credential.generation + 1
    assert result["credential"]["lease_id"] != abandoned.credential.lease_id
    assert result["document_state"]["snapshot_id"] == snapshot_id
    assert model.read_bytes() == original
    assert document.Modified is True


def test_gui_save_then_clean_acquire_avoids_identity_registration_deadlock(
    tmp_path, monkeypatch
):
    rpc, document, model, _original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    identity = service.identity_service.register_document(document)
    runtime = service.local_runtime_identity
    abandoned = service.begin_dirty_adoption(
        identity.session_uuid,
        LeaseOwner(
            addon_profile_id=runtime.addon_profile_id,
            addon_runtime_id=runtime.addon_runtime_id,
            freecad_pid=runtime.freecad_pid,
            freecad_process_started_at=runtime.freecad_process_started_at,
            boot_id=runtime.boot_id,
            mcp_instance_id="22222222-2222-4222-8222-222222222222",
            mcp_pid=202,
            mcp_process_started_at="2026-07-28T00:00:02Z",
            hostname=runtime.hostname,
            client="Claude",
            agent_id="claude-agent",
        ),
        document_dirty=True,
        local_confirmation=True,
    )
    observer = lease_observer.LeaseObserver(service_provider=lambda: service)

    observer.slotStartSaveDocument(document, document.FileName)
    replacement = tmp_path / "FreeCAD-save.FCStd"
    replacement.write_bytes(b"clean archive written through atomic replacement")
    model.unlink()
    replacement.replace(model)
    document.Modified = False
    refreshed = observer.slotFinishSaveDocument(document, document.FileName)
    assert refreshed.document.file_identity != identity.file_identity
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document, **_kwargs: str(uuid.uuid4()),
    )

    result = rpc.acquire_document_lock(
        selector={"document_name": document.Name},
        task_description="Continue after reconnect",
        client="GPT Sol",
        agent_id="gpt-sol-agent",
    )

    assert result["success"] is True, result
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["credential"]["generation"] == abandoned.credential.generation + 2
    assert result.get("error_code") != "LEASE_SERVICE_ERROR"
    assert "identity could not be registered" not in str(result)
    persisted = service.sidecar_store.read(sidecar_path_for(model))
    assert persisted.document.file_identity == refreshed.document.file_identity
    assert persisted.owner.client == "GPT Sol"


def test_close_reopen_then_clean_acquire_avoids_identity_registration_deadlock(
    tmp_path,
    monkeypatch,
):
    rpc, document, model, _original, service = _configure_dirty_adoption(
        monkeypatch,
        tmp_path,
    )
    identity = service.identity_service.register_document(document)
    runtime = service.local_runtime_identity
    abandoned = service.begin_dirty_adoption(
        identity.session_uuid,
        LeaseOwner(
            addon_profile_id=runtime.addon_profile_id,
            addon_runtime_id=runtime.addon_runtime_id,
            freecad_pid=runtime.freecad_pid,
            freecad_process_started_at=runtime.freecad_process_started_at,
            boot_id=runtime.boot_id,
            mcp_instance_id="22222222-2222-4222-8222-222222222222",
            mcp_pid=202,
            mcp_process_started_at="2026-07-28T00:00:02Z",
            hostname=runtime.hostname,
            client="Claude",
            agent_id="claude-agent",
        ),
        document_dirty=True,
        local_confirmation=True,
    )
    observer = lease_observer.LeaseObserver(service_provider=lambda: service)
    closed = observer.slotDeletedDocument(document)
    assert closed.state == LeaseState.USER_INTERVENED

    reopened = _DirtyDocument(model)
    reopened.Modified = False
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "getDocument",
        lambda name: reopened if name == reopened.Name else None,
    )
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "listDocuments",
        lambda: {reopened.Name: reopened},
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document: str(uuid.uuid4()),
    )

    result = rpc.acquire_document_lock(
        selector={"document_name": reopened.Name},
        task_description="Continue after close and reopen",
        client="Cursor",
        agent_id="cursor-agent",
    )

    assert result["success"] is True, result
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["credential"]["generation"] == abandoned.credential.generation + 2
    assert "identity could not be registered" not in str(result)
    persisted = service.sidecar_store.read(sidecar_path_for(model))
    assert persisted.document.session_uuid == identity.session_uuid
    assert persisted.owner.client == "Cursor"


def test_clean_acquire_self_recovers_missing_foreign_sidecar(
    tmp_path,
    monkeypatch,
):
    model = tmp_path / "OrphanedClean.FCStd"
    original = b"validated clean saved document"
    model.write_bytes(original)
    document = _DirtyDocument(model)
    document.Name = "OrphanedClean"
    document.Label = "Orphaned clean"
    document.Modified = False
    owner = LeaseOwner(
        addon_profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=42,
        freecad_process_started_at="2026-07-30T00:00:00Z",
        boot_id="test-boot",
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=202,
        mcp_process_started_at="2026-07-30T00:00:01Z",
        hostname=rpc_server.platform.node(),
        client="Claude",
        agent_id="claude-agent",
    )
    foreign_identities = DocumentIdentityService()
    foreign_document = foreign_identities.register(
        name=document.Name,
        path=model,
    )
    foreign_service = DocumentLeaseService(foreign_identities)
    foreign_grant = foreign_service.acquire(
        foreign_document.session_uuid,
        owner,
        snapshot_id=str(uuid.uuid4()),
    )

    identities = DocumentIdentityService()
    local_document = identities.register_document(document)
    runtime = SimpleNamespace(
        profile_id=owner.addon_profile_id,
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=owner.freecad_pid,
        freecad_process_started_at=owner.freecad_process_started_at,
        boot_id=owner.boot_id,
    )
    service = DocumentLeaseService(
        identities,
        SidecarStore(network_detector=lambda _path: False),
        local_runtime_identity=LocalRuntimeIdentity(
            addon_profile_id=runtime.profile_id,
            addon_runtime_id=runtime.addon_runtime_id,
            freecad_pid=runtime.freecad_pid,
            freecad_process_started_at=runtime.freecad_process_started_at,
            boot_id=runtime.boot_id,
            hostname=owner.hostname,
        ),
    )
    service.import_adjacent_foreign_recovery(
        local_document.session_uuid,
        live_document=local_document,
    )
    sidecar_path_for(model).unlink()

    rpc = _LegacyGlobalFixtureRPC()
    monkeypatch.setattr(
        rpc, "_dispatch_gui", lambda task, timeout=None, **_kwargs: task()
    )
    monkeypatch.setattr(rpc_server, "_import_document_lock", lambda: _DocumentLock())
    monkeypatch.setattr(rpc_server, "document_identity_service", identities)
    monkeypatch.setattr(rpc_server, "document_lease_service", service)
    monkeypatch.setattr(rpc_server, "rpc_runtime_manifest", runtime)
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "getDocument",
        lambda name: document if name == document.Name else None,
    )
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "listDocuments",
        lambda: {document.Name: document},
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document, **_kwargs: str(uuid.uuid4()),
    )

    result = rpc.acquire_document_lock(
        selector={"document_name": document.Name},
        task_description="Continue after missing sidecar",
        client="GPT Sol",
        agent_id="gpt-sol-agent",
    )

    assert result["success"] is True, result
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["credential"]["generation"] == (
        foreign_grant.credential.generation + 1
    )
    assert "DOCUMENT_IDENTITY_ERROR" not in str(result)
    assert "FOREIGN_SIDECAR_INVALID" not in str(result)
    assert model.read_bytes() == original
    persisted = service.sidecar_store.read(sidecar_path_for(model))
    assert persisted.document == local_document
    assert persisted.owner.addon_runtime_id == runtime.addon_runtime_id
    assert service.get_foreign_recovery(local_document.session_uuid) is None


def test_dirty_adoption_self_recovers_cached_worker_intervention_without_close(
    tmp_path,
    monkeypatch,
):
    model = tmp_path / "HamaAdapter.FCStd"
    original = b"validated saved Hama adapter"
    model.write_bytes(original)
    original_stat = model.stat()
    document = _DirtyDocument(model)
    document.Name = "HamaAdapter"
    document.Label = "Hama Adapter"
    document.Modified = True
    owner = LeaseOwner(
        addon_profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=42,
        freecad_process_started_at="2026-07-30T00:00:00Z",
        boot_id="test-boot",
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=202,
        mcp_process_started_at="2026-07-30T00:00:01Z",
        hostname=rpc_server.platform.node(),
        client="Claude",
        agent_id="claude-agent",
    )
    foreign_identities = DocumentIdentityService()
    foreign_document = foreign_identities.register(
        name=document.Name,
        path=model,
    )
    foreign_service = DocumentLeaseService(foreign_identities)
    foreign_grant = foreign_service.acquire(
        foreign_document.session_uuid,
        owner,
        snapshot_id=str(uuid.uuid4()),
    )
    intervened = foreign_service.takeover(
        foreign_document.session_uuid,
        dirty=False,
        reason=(
            "Unscoped FreeCAD save detected: "
            r"C:\Temp\freecad_mcp_workers\mcp_worker__legacy"
            r"\snapshots\0001_HamaAdapter.FCStd"
        ),
    )
    intervened = foreign_service.update_local_dirty(
        intervened.document.session_uuid,
        dirty=True,
    )
    assert intervened.validation_complete is False

    identities = DocumentIdentityService()
    local_document = identities.register_document(document)
    runtime = SimpleNamespace(
        profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=99,
        freecad_process_started_at="2026-07-30T00:10:00Z",
        boot_id=owner.boot_id,
    )
    service = DocumentLeaseService(
        identities,
        SidecarStore(network_detector=lambda _path: False),
        local_runtime_identity=LocalRuntimeIdentity(
            addon_profile_id=runtime.profile_id,
            addon_runtime_id=runtime.addon_runtime_id,
            freecad_pid=runtime.freecad_pid,
            freecad_process_started_at=runtime.freecad_process_started_at,
            boot_id=runtime.boot_id,
            hostname=owner.hostname,
        ),
        process_liveness_probe=lambda _pid: ProcessLivenessEvidence(False),
    )
    service.import_adjacent_foreign_recovery(
        local_document.session_uuid,
        live_document=local_document,
    )
    sidecar = sidecar_path_for(model)
    sidecar.unlink()

    rpc = _LegacyGlobalFixtureRPC()
    monkeypatch.setattr(
        rpc, "_dispatch_gui", lambda task, timeout=None, **_kwargs: task()
    )
    claims = AcquisitionClaimStore()
    monkeypatch.setattr(rpc_server, "_import_document_lock", lambda: _DocumentLock())
    monkeypatch.setattr(rpc_server, "document_identity_service", identities)
    monkeypatch.setattr(rpc_server, "document_lease_service", service)
    monkeypatch.setattr(rpc_server, "rpc_runtime_manifest", runtime)
    monkeypatch.setattr(rpc_server, "rpc_acquisition_claim_store", claims)
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "getDocument",
        lambda name: document if name == document.Name else None,
    )
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "listDocuments",
        lambda: {document.Name: document},
    )
    snapshot_id = str(uuid.uuid4())
    snapshots = []
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda doc, **kwargs: snapshots.append((doc, kwargs)) or snapshot_id,
    )
    confirmations = []
    monkeypatch.setattr(
        rpc_server,
        "_confirm_dirty_document_adoption_gui",
        lambda doc, identity: confirmations.append((doc, identity)) or True,
    )

    _DocumentLock.request_id = str(uuid.uuid4())
    clean_attempt = rpc.acquire_document_lock(
        selector={"document_name": document.Name},
        task_description="Must not relabel dirty state as clean",
    )
    assert clean_attempt["success"] is False
    assert clean_attempt["error_code"] == "DIRTY_REQUIRES_LOCAL_ADOPTION"
    assert not sidecar.exists()

    _DocumentLock.request_id = str(uuid.uuid4())
    request_id = _DocumentLock.request_id
    result = rpc.adopt_dirty_document(
        selector={"document_name": document.Name},
        task_description="Self-heal cached foreign worker intervention",
        client="GPT Sol",
        agent_id="gpt-sol-agent",
    )

    assert result["success"] is True, result
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["document_state"]["dirty"] is True
    assert result["document_state"]["user_intervened"] is False
    assert result["document_state"]["last_mutation_revision"] == 1
    assert result["document_state"]["last_verified_save_revision"] == 0
    assert result["document_state"]["snapshot_id"] == snapshot_id
    assert result["credential"]["generation"] == intervened.generation + 1
    assert "FOREIGN_SIDECAR_INVALID" not in str(result)
    assert snapshots == [
        (document, {"observer_request_id": request_id})
    ]
    assert confirmations == [(document, local_document)]
    assert document.Modified is True
    assert document.mutationAuthorityStatus() == {
        "owner": "mcp",
        "generation": result["credential"]["generation"],
        "provider_id": _DocumentLock.get_request_identity()["instance_id"],
        "restricted": True,
    }
    assert claims.claimable(
        _DocumentLock.get_request_identity()["instance_id"],
        request_id,
    )
    claimed = claims.claim(
        _DocumentLock.get_request_identity()["instance_id"],
        request_id,
    )
    assert claimed["credential"]["token"] == result["credential"]["token"]
    assert claimed["document_state"]["dirty"] is True
    persisted = service.sidecar_store.read(sidecar)
    assert persisted.document == local_document
    assert persisted.state == LeaseState.LOCKED_IDLE
    assert persisted.dirty is True
    assert persisted.snapshot_id == snapshot_id
    assert service.get_foreign_recovery(local_document.session_uuid) is None
    assert model.read_bytes() == original
    final_stat = model.stat()
    assert final_stat.st_size == original_stat.st_size
    assert final_stat.st_mtime_ns == original_stat.st_mtime_ns


@pytest.mark.parametrize(
    ("document_modified", "method_name"),
    [
        (False, "acquire_document_lock"),
        (True, "adopt_dirty_document"),
    ],
)
def test_acquisition_self_recovers_saved_acknowledged_dirty_sidecar(
    tmp_path,
    monkeypatch,
    document_modified,
    method_name,
):
    model = tmp_path / "SavedDirtyRecovery.FCStd"
    model.write_bytes(b"saved baseline before local takeover")
    document = _DirtyDocument(model)
    document.Name = "SavedDirtyRecovery"
    document.Label = "Saved dirty recovery"
    document.Modified = document_modified
    owner = LeaseOwner(
        addon_profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=42,
        freecad_process_started_at="2026-07-30T00:00:00Z",
        boot_id="test-boot",
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=202,
        mcp_process_started_at="2026-07-30T00:00:01Z",
        hostname=rpc_server.platform.node(),
        client="Claude",
        agent_id="claude-agent",
    )
    foreign_identities = DocumentIdentityService()
    foreign_document = foreign_identities.register(
        name=document.Name,
        path=model,
    )
    foreign_service = DocumentLeaseService(foreign_identities)
    foreign_grant = foreign_service.acquire(
        foreign_document.session_uuid,
        owner,
        snapshot_id=str(uuid.uuid4()),
    )
    taken = foreign_service.takeover(
        foreign_grant.credential.document_session_uuid,
        dirty=True,
        reason="Confirmed local GUI takeover",
    )
    acknowledged = foreign_service.acknowledge_local_dirty(
        taken.document.session_uuid,
        document_dirty=True,
        reason="Confirmed local GUI keep-dirty acknowledgement",
    )
    saved_bytes = b"user saved the recovered document before restarting FreeCAD"
    replacement = tmp_path / "SavedDirtyRecovery.replacement.FCStd"
    replacement.write_bytes(saved_bytes)
    os.replace(replacement, model)

    identities = DocumentIdentityService()
    local_document = identities.register_document(document)
    runtime = SimpleNamespace(
        profile_id=owner.addon_profile_id,
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=99,
        freecad_process_started_at="2026-07-30T00:10:00Z",
        boot_id=owner.boot_id,
    )
    service = DocumentLeaseService(
        identities,
        SidecarStore(network_detector=lambda _path: False),
        local_runtime_identity=LocalRuntimeIdentity(
            addon_profile_id=runtime.profile_id,
            addon_runtime_id=runtime.addon_runtime_id,
            freecad_pid=runtime.freecad_pid,
            freecad_process_started_at=runtime.freecad_process_started_at,
            boot_id=runtime.boot_id,
            hostname=owner.hostname,
        ),
        process_liveness_probe=lambda _pid: ProcessLivenessEvidence(exists=False),
    )
    rpc = _LegacyGlobalFixtureRPC()
    monkeypatch.setattr(
        rpc, "_dispatch_gui", lambda task, timeout=None, **_kwargs: task()
    )
    monkeypatch.setattr(rpc_server, "_import_document_lock", lambda: _DocumentLock())
    monkeypatch.setattr(rpc_server, "document_identity_service", identities)
    monkeypatch.setattr(rpc_server, "document_lease_service", service)
    monkeypatch.setattr(rpc_server, "rpc_runtime_manifest", runtime)
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "getDocument",
        lambda name: document if name == document.Name else None,
    )
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "listDocuments",
        lambda: {document.Name: document},
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document: str(uuid.uuid4()),
    )
    confirmations = []
    monkeypatch.setattr(
        rpc_server,
        "_confirm_dirty_document_adoption_gui",
        lambda doc, identity: confirmations.append((doc, identity)) or True,
    )

    result = getattr(rpc, method_name)(
        selector={"document_name": document.Name},
        task_description="Continue after the user saved and restarted",
        client="GPT Sol",
        agent_id="gpt-sol-agent",
    )

    assert result["success"] is True, result
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["document_state"]["dirty"] is document_modified
    assert result["credential"]["generation"] == acknowledged.generation + 1
    assert bool(confirmations) is document_modified
    assert model.read_bytes() == saved_bytes
    persisted = service.sidecar_store.read(sidecar_path_for(model))
    assert persisted.document == local_document
    assert persisted.owner.addon_runtime_id == runtime.addon_runtime_id
    assert persisted.state == LeaseState.LOCKED_IDLE
    assert service.get_foreign_recovery(local_document.session_uuid) is None


@pytest.mark.parametrize(
    ("document_modified", "method_name"),
    [
        (False, "acquire_document_lock"),
        (True, "adopt_dirty_document"),
    ],
)
def test_acquisition_self_recovers_abandoned_locked_error_sidecar(
    tmp_path,
    monkeypatch,
    document_modified,
    method_name,
):
    model = tmp_path / "AbandonedLockedError.FCStd"
    original = b"saved baseline before the failed edit"
    model.write_bytes(original)
    document = _DirtyDocument(model)
    document.Name = "AbandonedLockedError"
    document.Label = "Abandoned locked error"
    document.Modified = document_modified
    owner = LeaseOwner(
        addon_profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=42,
        freecad_process_started_at="2026-07-30T00:00:00Z",
        boot_id="test-boot",
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=202,
        mcp_process_started_at="2026-07-30T00:00:01Z",
        hostname=rpc_server.platform.node(),
        client="Claude",
        agent_id="claude-agent",
    )
    foreign_identities = DocumentIdentityService()
    foreign_document = foreign_identities.register(
        name=document.Name,
        path=model,
    )
    foreign_service = DocumentLeaseService(foreign_identities)
    foreign_grant = foreign_service.acquire(
        foreign_document.session_uuid,
        owner,
        snapshot_id=str(uuid.uuid4()),
    )
    foreign_service.begin_mutation(
        foreign_grant.credential,
        operation="Build feature",
    )
    errored = foreign_service.record_error(
        foreign_grant.credential,
        code="OPERATION_FAILED",
        message="guard rejected the build after rollback",
        dirty=True,
    )

    identities = DocumentIdentityService()
    local_document = identities.register_document(document)
    runtime = SimpleNamespace(
        profile_id=owner.addon_profile_id,
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=99,
        freecad_process_started_at="2026-07-30T00:10:00Z",
        boot_id=owner.boot_id,
    )
    service = DocumentLeaseService(
        identities,
        SidecarStore(network_detector=lambda _path: False),
        local_runtime_identity=LocalRuntimeIdentity(
            addon_profile_id=runtime.profile_id,
            addon_runtime_id=runtime.addon_runtime_id,
            freecad_pid=runtime.freecad_pid,
            freecad_process_started_at=runtime.freecad_process_started_at,
            boot_id=runtime.boot_id,
            hostname=owner.hostname,
        ),
        process_liveness_probe=lambda _pid: ProcessLivenessEvidence(exists=False),
    )
    service.import_adjacent_foreign_recovery(
        local_document.session_uuid,
        live_document=local_document,
    )

    rpc = _LegacyGlobalFixtureRPC()
    monkeypatch.setattr(
        rpc, "_dispatch_gui", lambda task, timeout=None, **_kwargs: task()
    )
    monkeypatch.setattr(rpc_server, "_import_document_lock", lambda: _DocumentLock())
    monkeypatch.setattr(rpc_server, "document_identity_service", identities)
    monkeypatch.setattr(rpc_server, "document_lease_service", service)
    monkeypatch.setattr(rpc_server, "rpc_runtime_manifest", runtime)
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "getDocument",
        lambda name: document if name == document.Name else None,
    )
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "listDocuments",
        lambda: {document.Name: document},
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document: str(uuid.uuid4()),
    )
    confirmations = []
    monkeypatch.setattr(
        rpc_server,
        "_confirm_dirty_document_adoption_gui",
        lambda doc, identity: confirmations.append((doc, identity)) or True,
    )

    result = getattr(rpc, method_name)(
        selector={"document_name": document.Name},
        task_description="Continue after closing the failed edit without saving",
        client="GPT Sol",
        agent_id="gpt-sol-agent",
    )

    assert result["success"] is True, result
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["document_state"]["dirty"] is document_modified
    assert result["credential"]["generation"] == errored.generation + 1
    assert bool(confirmations) is document_modified
    assert model.read_bytes() == original
    persisted = service.sidecar_store.read(sidecar_path_for(model))
    assert persisted.document == local_document
    assert persisted.owner.addon_runtime_id == runtime.addon_runtime_id
    assert persisted.state == LeaseState.LOCKED_IDLE
    assert service.get_foreign_recovery(local_document.session_uuid) is None


def test_dirty_adoption_rolls_back_if_saved_baseline_changes_before_promotion(
    tmp_path, monkeypatch
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    snapshot_id = str(uuid.uuid4())
    discarded = []
    monkeypatch.setattr(
        rpc_server, "_confirm_dirty_document_adoption_gui", lambda *_args: True
    )

    def snapshot_then_replace_saved_file(_document):
        model.write_bytes(original + b" externally replaced")
        return snapshot_id

    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        snapshot_then_replace_saved_file,
    )
    monkeypatch.setattr(
        rpc_server,
        "discard_lease_baseline_snapshot",
        lambda opaque_id: discarded.append(opaque_id),
    )

    result = rpc.adopt_dirty_document(selector={"document_name": document.Name})

    assert result["success"] is False
    assert result["error_code"] == "LEASE_COORDINATION_LOST"
    assert "saved document changed during acquisition" in result["error"]
    assert discarded == [snapshot_id]
    assert service.list_records() == []
    assert not sidecar_path_for(model).exists()
    assert document.Modified is True


def test_process_exit_after_snapshot_checkpoint_preserves_recovery_authority(
    tmp_path,
    monkeypatch,
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch,
        tmp_path,
    )
    snapshot_id = str(uuid.uuid4())
    monkeypatch.setattr(
        rpc_server,
        "_confirm_dirty_document_adoption_gui",
        lambda *_args: True,
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document: snapshot_id,
    )

    def exit_before_promotion(*_args, **_kwargs):
        raise SystemExit("simulated FreeCAD process exit")

    monkeypatch.setattr(
        service,
        "complete_dirty_adoption",
        exit_before_promotion,
    )

    with pytest.raises(SystemExit, match="simulated FreeCAD process exit"):
        rpc.adopt_dirty_document(
            selector={"document_name": document.Name},
            client="Claude",
        )

    persisted = service.sidecar_store.read(sidecar_path_for(model))
    assert persisted.state == LeaseState.ACQUIRING
    assert persisted.snapshot_id == snapshot_id
    assert persisted.dirty is True
    assert model.read_bytes() == original
    with pytest.raises(LeaseConflictError, match="already has a lease"):
        service.begin_dirty_adoption(
            persisted.document.session_uuid,
            LeaseOwner(
                addon_profile_id=str(uuid.uuid4()),
                addon_runtime_id=str(uuid.uuid4()),
                freecad_pid=42,
                freecad_process_started_at="2026-07-28T00:00:00Z",
                boot_id="test-boot",
                mcp_instance_id="33333333-3333-4333-8333-333333333333",
                mcp_pid=303,
                mcp_process_started_at="2026-07-28T00:00:03Z",
                hostname=service.local_runtime_identity.hostname,
                client="Cursor",
                agent_id="cursor-agent",
            ),
            document_dirty=True,
            local_confirmation=True,
        )


def test_dirty_adoption_auto_confirms_without_dialog(monkeypatch):
    """Starting an agent implies write intent; no FreeCAD pop-up is shown."""

    boxes = []

    class Application:
        @staticmethod
        def instance():
            return object()

    class MessageBox:
        Warning = 1
        Yes = 2
        Cancel = 4

        def __init__(self):
            boxes.append(self)

        def exec(self):
            raise AssertionError("dirty adoption must not open a QMessageBox")

    monkeypatch.setattr(
        rpc_server,
        "QtWidgets",
        SimpleNamespace(
            QApplication=Application,
            QMessageBox=MessageBox,
            QCheckBox=object,
        ),
    )
    document = SimpleNamespace(Label="Dirty model")
    identity = SimpleNamespace(name="DirtyModel", canonical_path="DirtyModel.FCStd")

    assert rpc_server._confirm_dirty_document_adoption_gui(document, identity) is True
    assert rpc_server._confirm_dirty_document_adoption_gui(document, identity) is True
    assert boxes == []


def test_locked_error_handoff_auto_authorizes_without_dialog(monkeypatch):
    """Agent-start handoff must not construct or execute a message box."""

    boxes = []

    class Application:
        @staticmethod
        def instance():
            return object()

    class MessageBox:
        Warning = 1
        Yes = 2
        Cancel = 4

        def __init__(self):
            boxes.append(self)

        def exec(self):
            raise AssertionError("LOCKED_ERROR handoff must not open a QMessageBox")

    monkeypatch.setattr(
        rpc_server,
        "QtWidgets",
        SimpleNamespace(
            QApplication=Application,
            QMessageBox=MessageBox,
            QCheckBox=object,
        ),
    )
    document = SimpleNamespace(Label="Dirty model")
    identity = SimpleNamespace(name="DirtyModel", canonical_path="DirtyModel.FCStd")

    assert rpc_server._authorize_locked_error_handoff_gui(document, identity) is True
    assert rpc_server._authorize_locked_error_handoff_gui(document, identity) is True
    assert boxes == []


def test_cancelled_dirty_snapshot_rolls_back_without_orphan(tmp_path, monkeypatch):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        rpc_server, "_confirm_dirty_document_adoption_gui", lambda *_args: True
    )
    discarded = []
    snapshot_id = str(uuid.uuid4())
    registry = InflightRequestRegistry()
    inflight = registry.register(
        "rpc-session",
        _DocumentLock.request_id,
        "adopt_dirty_document",
        lease_affecting=True,
    )

    def snapshot_then_cancel(_document):
        assert inflight.token.request_cancel()[0] is True
        return snapshot_id

    monkeypatch.setattr(
        rpc_server, "create_lease_baseline_snapshot_gui", snapshot_then_cancel
    )
    monkeypatch.setattr(
        rpc_server,
        "discard_lease_baseline_snapshot",
        lambda opaque_id: discarded.append(opaque_id),
    )
    monkeypatch.setattr(rpc_server, "rpc_inflight_request_registry", registry)
    rpc._inflight_context.value = inflight
    try:
        with pytest.raises(Exception) as failure:
            rpc.adopt_dirty_document(selector={"document_name": document.Name})
    finally:
        del rpc._inflight_context.value

    assert failure.value.__class__.__name__ == "RequestCancellationError"
    assert inflight.token.snapshot().mutation_started is False
    assert inflight.token.cancellation_resolution()[0]["rolled_back"] is True
    assert discarded == [snapshot_id]
    assert service.list_records() == []
    assert not sidecar_path_for(model).exists()
    assert model.read_bytes() == original
    assert document.Modified is True


def test_slow_confirmation_outside_backend_budget_does_not_publish_acquiring(
    tmp_path, monkeypatch
):
    """Initial unlocked dirty adoption has no confirmation GUI phase."""

    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    submit_timeouts = []

    class _Dispatcher:
        def submit(self, task, timeout, **_kwargs):
            name = getattr(task, "__name__", "")
            submit_timeouts.append((name, timeout))
            return task()

    monkeypatch.setattr(rpc_server, "gui_dispatcher", _Dispatcher())
    # Undo _configure_dirty_adoption's stub so real timeout conversion runs.
    monkeypatch.setattr(
        rpc,
        "_dispatch_gui",
        rpc_server.FreeCADRPC._dispatch_gui.__get__(rpc, rpc_server.FreeCADRPC),
    )
    monkeypatch.setattr(
        rpc_server, "_confirm_dirty_document_adoption_gui", lambda *_args: True
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document: str(uuid.uuid4()),
    )

    result = rpc.adopt_dirty_document(selector={"document_name": document.Name})

    assert result["success"] is True
    assert not any(name == "confirm_gui" for name, _timeout in submit_timeouts)
    assert any(
        name == "reserve_gui" and timeout == rpc.ACQUIRE_GUI_PHASE_TIMEOUT_S
        for name, timeout in submit_timeouts
    )
    assert (
        rpc.ACQUIRE_GUI_PHASE_TIMEOUT_S * 2 + rpc.ACQUIRE_HASH_TIMEOUT_S
        <= rpc.CLIENT_LIFECYCLE_TIMEOUT_S
    )
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert model.read_bytes() == original


def test_client_timeout_after_acquiring_allows_same_owner_retry(
    tmp_path, monkeypatch
):
    """Interrupted adoption after ACQUIRING must not require the 90s stale wait."""

    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        rpc_server, "_confirm_dirty_document_adoption_gui", lambda *_args: True
    )
    runtime = service.local_runtime_identity
    identity = service.identity_service.register_document(document)
    abandoned_request_id = str(uuid.uuid4())
    abandoned = service.begin_dirty_adoption(
        identity.session_uuid,
        LeaseOwner(
            addon_profile_id=runtime.addon_profile_id,
            addon_runtime_id=runtime.addon_runtime_id,
            freecad_pid=runtime.freecad_pid,
            freecad_process_started_at=runtime.freecad_process_started_at,
            boot_id=runtime.boot_id,
            mcp_instance_id=_DocumentLock.get_request_identity()["instance_id"],
            mcp_pid=101,
            mcp_process_started_at="2026-07-28T00:00:01Z",
            hostname=runtime.hostname,
            client="pytest",
            agent_id="agent-a",
        ),
        document_dirty=True,
        local_confirmation=True,
        acquisition_request_id=abandoned_request_id,
        live_acquisition_request_ids=frozenset(),
    )
    assert abandoned.record.state == LeaseState.ACQUIRING
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document: str(uuid.uuid4()),
    )

    result = rpc.adopt_dirty_document(selector={"document_name": document.Name})

    assert result["success"] is True
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["credential"]["generation"] == abandoned.record.generation + 1
    with pytest.raises(AuthorizationError):
        service.authorize(abandoned.credential)
    assert model.read_bytes() == original


def test_same_runtime_live_acquiring_is_not_fenced_by_concurrent_request(
    tmp_path, monkeypatch
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        rpc_server, "_confirm_dirty_document_adoption_gui", lambda *_args: True
    )
    runtime = service.local_runtime_identity
    identity = service.identity_service.register_document(document)
    live_request_id = _DocumentLock.request_id
    service.begin_dirty_adoption(
        identity.session_uuid,
        LeaseOwner(
            addon_profile_id=runtime.addon_profile_id,
            addon_runtime_id=runtime.addon_runtime_id,
            freecad_pid=runtime.freecad_pid,
            freecad_process_started_at=runtime.freecad_process_started_at,
            boot_id=runtime.boot_id,
            mcp_instance_id=_DocumentLock.get_request_identity()["instance_id"],
            mcp_pid=101,
            mcp_process_started_at="2026-07-28T00:00:01Z",
            hostname=runtime.hostname,
            client="pytest",
            agent_id="agent-a",
        ),
        document_dirty=True,
        local_confirmation=True,
        acquisition_request_id=live_request_id,
        live_acquisition_request_ids=frozenset(),
    )
    registry = InflightRequestRegistry()
    registry.register(
        "rpc-session",
        live_request_id,
        "adopt_dirty_document",
        lease_affecting=True,
    )
    monkeypatch.setattr(rpc_server, "rpc_inflight_request_registry", registry)

    result = rpc.adopt_dirty_document(selector={"document_name": document.Name})

    assert result["success"] is False
    assert result["error_code"] == "LEASE_CONFLICT"
    assert model.read_bytes() == original


def test_foreign_live_acquiring_is_not_fenced_by_local_retry(tmp_path, monkeypatch):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        rpc_server, "_confirm_dirty_document_adoption_gui", lambda *_args: True
    )
    runtime = service.local_runtime_identity
    identity = service.identity_service.register_document(document)
    foreign = service.begin_dirty_adoption(
        identity.session_uuid,
        LeaseOwner(
            addon_profile_id=runtime.addon_profile_id,
            addon_runtime_id=runtime.addon_runtime_id,
            freecad_pid=runtime.freecad_pid,
            freecad_process_started_at=runtime.freecad_process_started_at,
            boot_id=runtime.boot_id,
            mcp_instance_id=str(uuid.uuid4()),
            mcp_pid=999,
            mcp_process_started_at="2026-07-28T00:00:01Z",
            hostname=runtime.hostname,
            client="foreign",
            agent_id="agent-b",
        ),
        document_dirty=True,
        local_confirmation=True,
    )

    result = rpc.adopt_dirty_document(selector={"document_name": document.Name})

    assert result["success"] is False
    assert result["error_code"] == "LEASE_CONFLICT"
    assert service.get(identity.session_uuid)["lease_id"] == foreign.record.lease_id
    assert model.read_bytes() == original


def test_clean_acquire_never_opens_adoption_dialog(tmp_path, monkeypatch):
    model = tmp_path / "CleanModel.FCStd"
    model.write_bytes(b"clean baseline")
    document = _DirtyDocument(model)
    document.Name = "CleanModel"
    document.Modified = False
    identities = DocumentIdentityService()
    runtime = SimpleNamespace(
        profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=42,
        freecad_process_started_at="2026-07-28T00:00:00Z",
        boot_id="test-boot",
    )
    service = DocumentLeaseService(
        identities,
        SidecarStore(network_detector=lambda _path: False),
        local_runtime_identity=LocalRuntimeIdentity(
            addon_profile_id=runtime.profile_id,
            addon_runtime_id=runtime.addon_runtime_id,
            freecad_pid=runtime.freecad_pid,
            freecad_process_started_at=runtime.freecad_process_started_at,
            boot_id=runtime.boot_id,
            hostname=rpc_server.platform.node(),
        ),
    )
    rpc = _LegacyGlobalFixtureRPC()
    monkeypatch.setattr(
        rpc, "_dispatch_gui", lambda task, timeout=None, **_kwargs: task()
    )
    monkeypatch.setattr(rpc_server, "_import_document_lock", lambda: _DocumentLock())
    monkeypatch.setattr(rpc_server, "document_identity_service", identities)
    monkeypatch.setattr(rpc_server, "document_lease_service", service)
    monkeypatch.setattr(rpc_server, "rpc_runtime_manifest", runtime)
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "getDocument",
        lambda name: document if name == document.Name else None,
    )
    monkeypatch.setattr(
        rpc_server.FreeCAD, "listDocuments", lambda: {document.Name: document}
    )
    dialog_calls = []

    def unexpected_dialog(*_args):
        dialog_calls.append(True)
        return True

    monkeypatch.setattr(
        rpc_server, "_confirm_dirty_document_adoption_gui", unexpected_dialog
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document: str(uuid.uuid4()),
    )

    result = rpc.acquire_document_lock(doc_name=document.Name)

    assert result["success"] is True
    assert dialog_calls == []
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value


def test_cancelled_before_snapshot_rolls_back_acquiring(tmp_path, monkeypatch):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        rpc_server, "_confirm_dirty_document_adoption_gui", lambda *_args: True
    )
    registry = InflightRequestRegistry()
    inflight = registry.register(
        "rpc-session",
        _DocumentLock.request_id,
        "adopt_dirty_document",
        lease_affecting=True,
    )

    def cancel_before_snapshot(_document):
        assert inflight.token.request_cancel()[0] is True
        inflight.token.checkpoint("acquisition_snapshot_gui")
        return str(uuid.uuid4())

    monkeypatch.setattr(
        rpc_server, "create_lease_baseline_snapshot_gui", cancel_before_snapshot
    )
    monkeypatch.setattr(rpc_server, "rpc_inflight_request_registry", registry)
    rpc._inflight_context.value = inflight
    try:
        with pytest.raises(Exception) as failure:
            rpc.adopt_dirty_document(selector={"document_name": document.Name})
    finally:
        del rpc._inflight_context.value

    assert failure.value.__class__.__name__ == "RequestCancellationError"
    assert service.list_records() == []
    assert not sidecar_path_for(model).exists()
    assert model.read_bytes() == original


def test_hash_timeout_aborts_acquiring_without_long_wait(tmp_path, monkeypatch):
    """Off-GUI hash must abort ACQUIRING inside ACQUIRE_HASH_TIMEOUT_S."""

    import time

    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        rpc_server, "_confirm_dirty_document_adoption_gui", lambda *_args: True
    )
    monkeypatch.setattr(rpc, "ACQUIRE_HASH_TIMEOUT_S", 0.05)
    lease_mod = rpc_server._import_document_lease()

    def hang_hash(*_args, **_kwargs):
        time.sleep(5)
        return capture_file_baseline(str(model))

    monkeypatch.setattr(lease_mod, "capture_file_baseline", hang_hash)

    started = time.monotonic()
    result = rpc.adopt_dirty_document(selector={"document_name": document.Name})
    elapsed = time.monotonic() - started

    assert result["success"] is False
    assert "hash" in str(result.get("error") or "").lower() or "budget" in str(
        result.get("error") or ""
    ).lower()
    assert elapsed < 2.0
    assert service.list_records() == []
    assert not sidecar_path_for(model).exists()
    assert model.read_bytes() == original
    assert document.Modified is True


def test_cancel_claimable_handoff_with_completed_tombstone_is_not_cancellable(
    tmp_path, monkeypatch
):
    """IR completed tombstone must not mask REQUEST_NOT_CANCELLABLE."""

    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    identity, _baseline, _snapshot_id, active, _errored = _seed_locked_error_for_handoff(
        service, document, model
    )

    def sync_start(**kwargs):
        rpc_server.rpc_handoff_continuation_store.begin(
            mcp_runtime_id=kwargs["mcp_runtime_id"],
            request_id=kwargs["request_id"],
        )
        rpc._run_locked_error_handoff_continuation(**kwargs)

    monkeypatch.setattr(rpc, "_start_locked_error_handoff_continuation", sync_start)

    pending = rpc.adopt_dirty_document(selector={"document_name": document.Name})
    assert pending["error_code"] == "LOCKED_ERROR_HANDOFF_PENDING"
    request_id = pending["request_id"]
    runtime_id = _DocumentLock.get_request_identity()["instance_id"]
    session_id = _DocumentLock.get_request_identity()["authenticated_session_id"]

    continuation = _await_handoff_claimable(runtime_id, request_id)
    assert continuation is not None
    assert continuation.state == "claimable"

    # Simulate the detect handler's process-pinned completed tombstone.
    registry = InflightRequestRegistry()
    inflight = registry.register(
        session_id, request_id, "adopt_dirty_document", lease_affecting=True
    )
    inflight.token.finish_handler("completed")
    monkeypatch.setattr(rpc_server, "rpc_inflight_request_registry", registry)

    cancelled = rpc.cancel_request(request_id)
    assert cancelled["success"] is False
    assert cancelled["error_code"] == "REQUEST_NOT_CANCELLABLE"
    assert "claim_acquisition_result" in cancelled["error"]
    assert cancelled.get("handoff_cancelled") is False
    assert rpc_server.rpc_acquisition_claim_store.claimable(runtime_id, request_id)
    with pytest.raises(AuthorizationError):
        service.authorize(active.credential)
    assert model.read_bytes() == original
    assert identity.session_uuid


def test_cancel_failed_handoff_returns_terminal_failure_details(
    tmp_path, monkeypatch
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    _seed_locked_error_for_handoff(service, document, model)
    monkeypatch.setattr(
        rpc_server, "_authorize_locked_error_handoff_gui", lambda *_args: False
    )

    def sync_start(**kwargs):
        rpc_server.rpc_handoff_continuation_store.begin(
            mcp_runtime_id=kwargs["mcp_runtime_id"],
            request_id=kwargs["request_id"],
        )
        rpc._run_locked_error_handoff_continuation(**kwargs)

    monkeypatch.setattr(rpc, "_start_locked_error_handoff_continuation", sync_start)

    pending = rpc.adopt_dirty_document(selector={"document_name": document.Name})
    request_id = pending["request_id"]
    runtime_id = _DocumentLock.get_request_identity()["instance_id"]
    continuation = _await_handoff_claimable(runtime_id, request_id)
    assert continuation is not None
    assert continuation.state == "denied"

    cancelled = rpc.cancel_request(request_id)
    assert cancelled["success"] is False
    assert cancelled["error_code"] == "DIRTY_ADOPTION_PRECONDITION_FAILED"
    assert "not authorized" in cancelled["error"].lower()
    assert "claim the escrowed" not in cancelled["error"].lower()
    assert cancelled["cancellation"]["status"] == "terminal_denied"
    assert model.read_bytes() == original


def test_claim_acquisition_result_reports_running_and_failed_continuations(
    tmp_path, monkeypatch
):
    rpc, document, _model, _original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    _seed_locked_error_for_handoff(service, document, _model)
    runtime_id = _DocumentLock.get_request_identity()["instance_id"]
    request_id = str(uuid.uuid4())
    store = rpc_server.rpc_handoff_continuation_store
    store.begin(mcp_runtime_id=runtime_id, request_id=request_id)
    store.update(
        runtime_id, request_id, state="authorizing", stage="handoff_authorize"
    )

    pending = rpc.claim_acquisition_result(request_id)
    assert pending["success"] is False
    assert pending["pending"] is True
    assert pending["error_code"] == "ACQUISITION_CLAIM_PENDING"

    store.update(
        runtime_id,
        request_id,
        state="failed",
        stage="handoff_failed",
        error_code="LEASE_CONFLICT",
        error="CAS failed after begin_claim",
    )
    failed = rpc.claim_acquisition_result(request_id)
    assert failed["success"] is False
    assert failed["error_code"] == "LEASE_CONFLICT"
    assert "CAS failed" in failed["error"]


def test_claim_missing_escrow_marks_continuation_credential_unavailable(
    tmp_path, monkeypatch
):
    rpc, document, _model, _original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    _seed_locked_error_for_handoff(service, document, _model)
    runtime_id = _DocumentLock.get_request_identity()["instance_id"]
    request_id = str(uuid.uuid4())
    store = rpc_server.rpc_handoff_continuation_store
    store.begin(mcp_runtime_id=runtime_id, request_id=request_id)
    store.update(runtime_id, request_id, state="claimable", stage="handoff_complete")

    missing = rpc.claim_acquisition_result(request_id)
    assert missing["success"] is False
    assert missing["error_code"] == "ACQUISITION_CREDENTIAL_UNAVAILABLE"
    assert missing.get("recovery_required") is True
    continuation = store.get(runtime_id, request_id)
    assert continuation is not None
    assert continuation.state == "failed"
    assert continuation.error_code == "ACQUISITION_CREDENTIAL_UNAVAILABLE"


def test_successful_claim_ack_marks_continuation_claimed(tmp_path, monkeypatch):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    _seed_locked_error_for_handoff(service, document, model)

    def sync_start(**kwargs):
        rpc_server.rpc_handoff_continuation_store.begin(
            mcp_runtime_id=kwargs["mcp_runtime_id"],
            request_id=kwargs["request_id"],
        )
        rpc._run_locked_error_handoff_continuation(**kwargs)

    monkeypatch.setattr(rpc, "_start_locked_error_handoff_continuation", sync_start)

    pending = rpc.adopt_dirty_document(selector={"document_name": document.Name})
    request_id = pending["request_id"]
    runtime_id = _DocumentLock.get_request_identity()["instance_id"]
    continuation = _await_handoff_claimable(runtime_id, request_id)
    assert continuation is not None and continuation.state == "claimable"

    claimed = rpc.claim_acquisition_result(request_id)
    assert claimed["success"] is True
    ack = rpc.acknowledge_acquisition_claim(request_id)
    assert ack["acknowledged"] is True
    after = rpc_server.rpc_handoff_continuation_store.get(runtime_id, request_id)
    assert after is not None
    assert after.state == "claimed"
    status = rpc.get_request_status(request_id)
    assert status["state"] == "completed"
    assert status["handoff_continuation"]["state"] == "claimed"
    assert model.read_bytes() == original


def test_create_document_begin_acquisition_passes_fencing_request_ids(
    tmp_path, monkeypatch
):
    rpc, document, _model, _original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    created = SimpleNamespace(
        Name="FreshDoc", Label="Fresh", FileName="", Modified=False, Objects=()
    )
    captured = {}
    seen = {"created": False}

    def fake_begin(selector, owner, **kwargs):
        captured["selector"] = selector
        captured["owner"] = owner
        captured.update(kwargs)
        raise RuntimeError("stop after fencing capture")

    def get_document(name):
        if name == "FreshDoc":
            return created if seen["created"] else None
        return document if name == document.Name else None

    monkeypatch.setattr(rpc_server.FreeCAD, "getDocument", get_document)
    monkeypatch.setattr(
        rpc,
        "_create_document_gui",
        lambda _name: seen.__setitem__("created", True) or True,
    )
    monkeypatch.setattr(
        rpc_server,
        "_ensure_v2_document",
        lambda doc: service.identity_service.register_document(doc),
    )
    monkeypatch.setattr(service, "begin_acquisition", fake_begin)
    registry = InflightRequestRegistry()
    registry.register(
        "rpc-session",
        "live-create-sibling",
        "create_document",
        lease_affecting=True,
    )
    monkeypatch.setattr(rpc_server, "rpc_inflight_request_registry", registry)
    _DocumentLock.request_id = "create-fencing-request"

    result = rpc.create_document("FreshDoc")
    assert result["success"] is False
    assert captured["acquisition_request_id"] == "create-fencing-request"
    assert "live-create-sibling" in set(captured["live_acquisition_request_ids"])


def test_escrow_failure_after_handoff_cas_marks_recovery_required(
    tmp_path, monkeypatch
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
    identity, _baseline, _snapshot_id, active, _errored = _seed_locked_error_for_handoff(
        service, document, model
    )

    def boom_store(**_kwargs):
        raise RuntimeError("vault write failed")

    monkeypatch.setattr(
        rpc_server.rpc_acquisition_claim_store, "store", boom_store
    )

    def sync_start(**kwargs):
        rpc_server.rpc_handoff_continuation_store.begin(
            mcp_runtime_id=kwargs["mcp_runtime_id"],
            request_id=kwargs["request_id"],
        )
        rpc._run_locked_error_handoff_continuation(**kwargs)

    monkeypatch.setattr(rpc, "_start_locked_error_handoff_continuation", sync_start)

    pending = rpc.adopt_dirty_document(selector={"document_name": document.Name})
    request_id = pending["request_id"]
    runtime_id = _DocumentLock.get_request_identity()["instance_id"]
    continuation = _await_handoff_claimable(runtime_id, request_id)
    assert continuation is not None
    assert continuation.state == "failed"
    assert continuation.error_code == "ACQUISITION_CREDENTIAL_ESCROW_FAILED"
    assert "recovery" in str(continuation.error or "").lower()
    assert not rpc_server.rpc_acquisition_claim_store.claimable(
        runtime_id, request_id
    )
    # Ownership already rotated despite escrow failure.
    assert service.get(identity.session_uuid)["lease"]["state"] == (
        LeaseState.LOCKED_IDLE.value
    )
    with pytest.raises(AuthorizationError):
        service.authorize(active.credential)
    assert model.read_bytes() == original
