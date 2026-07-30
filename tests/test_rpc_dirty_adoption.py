"""Focused RPC tests for initial dirty-document lease adoption."""

from __future__ import annotations

import os
import uuid
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
    SidecarStore,
    capture_file_baseline,
    sidecar_path_for,
)
from addon.FreeCADMCP.document_lease import observer as lease_observer
from addon.FreeCADMCP.rpc_server import rpc_server
from addon.FreeCADMCP.rpc_server.inflight_requests import InflightRequestRegistry

pytestmark = pytest.mark.unit


class _DirtyDocument:
    def __init__(self, path):
        self.Name = "DirtyModel"
        self.Label = "Dirty model"
        self.FileName = str(path)
        self.Modified = True


class _DocumentLock:
    @staticmethod
    def is_enabled():
        return True

    @staticmethod
    def get_request_identity():
        return {
            "request_id": "dirty-adoption-request",
            "authenticated_session_id": "rpc-session",
            "instance_id": "11111111-1111-4111-8111-111111111111",
            "pid": 101,
            "mcp_process_started_at": "2026-07-28T00:00:01Z",
            "client": "pytest",
            "agent_id": "agent-a",
        }

    @staticmethod
    def begin_agent_mutation_scope(_request_id, _document_keys):
        return True

    @staticmethod
    def end_agent_mutation_scope(_request_id, _document_keys):
        return True


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
    rpc = rpc_server.FreeCADRPC()
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, timeout=None: task())
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
    return rpc, document, model, original, service


def test_dirty_adoption_requires_local_confirmation(tmp_path, monkeypatch):
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


def test_confirmed_dirty_adoption_handoffs_local_locked_error(
    tmp_path,
    monkeypatch,
):
    rpc, document, model, original, service = _configure_dirty_adoption(
        monkeypatch, tmp_path
    )
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
    monkeypatch.setattr(
        rpc_server, "_confirm_dirty_document_adoption_gui", lambda *_args: True
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        lambda _document: pytest.fail("handoff must preserve the existing snapshot"),
    )

    result = rpc.adopt_dirty_document(
        selector={"document_name": document.Name},
        task_description="Continue after typed operation rollback",
    )

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
        lambda _document: str(uuid.uuid4()),
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

    rpc = rpc_server.FreeCADRPC()
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, timeout=None: task())
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
    rpc = rpc_server.FreeCADRPC()
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, timeout=None: task())
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

    rpc = rpc_server.FreeCADRPC()
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, timeout=None: task())
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


def test_dirty_adoption_dialog_can_suppress_repeat_prompts_for_session(monkeypatch):
    boxes = []

    class Application:
        @staticmethod
        def instance():
            return object()

    class CheckBox:
        def __init__(self, text, parent):
            self.text = text
            self.parent = parent

        @staticmethod
        def isChecked():
            return True

    class MessageBox:
        Warning = 1
        Yes = 2
        Cancel = 4

        def __init__(self):
            boxes.append(self)

        def setIcon(self, value):
            self.icon = value

        def setWindowTitle(self, value):
            self.title = value

        def setText(self, value):
            self.text = value

        def setStandardButtons(self, value):
            self.buttons = value

        def setDefaultButton(self, value):
            self.default = value

        def setCheckBox(self, value):
            self.checkbox = value

        def exec(self):
            return self.Yes

    monkeypatch.setattr(
        rpc_server,
        "QtWidgets",
        SimpleNamespace(
            QApplication=Application,
            QMessageBox=MessageBox,
            QCheckBox=CheckBox,
        ),
    )
    monkeypatch.setattr(rpc_server, "_confirm_dirty_adoption_for_session", False)
    document = SimpleNamespace(Label="Dirty model")
    identity = SimpleNamespace(name="DirtyModel", canonical_path="DirtyModel.FCStd")

    assert rpc_server._confirm_dirty_document_adoption_gui(document, identity) is True
    assert rpc_server._confirm_dirty_document_adoption_gui(document, identity) is True
    assert len(boxes) == 1
    assert "Don't ask again" in boxes[0].checkbox.text
    assert rpc_server._confirm_dirty_adoption_for_session is True


@pytest.mark.parametrize(
    (
        "response_name",
        "checked",
        "expected_results",
        "expected_dialogs",
        "expected_suppressed",
    ),
    [
        ("Yes", False, [True, True], 2, False),
        ("Cancel", True, [False, False], 2, False),
    ],
)
def test_dirty_adoption_dialog_only_suppresses_confirmed_checked_choice(
    monkeypatch,
    response_name,
    checked,
    expected_results,
    expected_dialogs,
    expected_suppressed,
):
    boxes = []

    class Application:
        @staticmethod
        def instance():
            return object()

    class CheckBox:
        def __init__(self, _text, _parent):
            pass

        @staticmethod
        def isChecked():
            return checked

    class MessageBox:
        Warning = 1
        Yes = 2
        Cancel = 4

        def __init__(self):
            boxes.append(self)

        def setIcon(self, _value):
            pass

        def setWindowTitle(self, _value):
            pass

        def setText(self, _value):
            pass

        def setStandardButtons(self, _value):
            pass

        def setDefaultButton(self, _value):
            pass

        def setCheckBox(self, _value):
            pass

        def exec(self):
            return getattr(self, response_name)

    monkeypatch.setattr(
        rpc_server,
        "QtWidgets",
        SimpleNamespace(
            QApplication=Application,
            QMessageBox=MessageBox,
            QCheckBox=CheckBox,
        ),
    )
    monkeypatch.setattr(rpc_server, "_confirm_dirty_adoption_for_session", False)
    document = SimpleNamespace(Label="Dirty model")
    identity = SimpleNamespace(name="DirtyModel", canonical_path="DirtyModel.FCStd")

    results = [
        rpc_server._confirm_dirty_document_adoption_gui(document, identity),
        rpc_server._confirm_dirty_document_adoption_gui(document, identity),
    ]

    assert results == expected_results
    assert len(boxes) == expected_dialogs
    assert rpc_server._confirm_dirty_adoption_for_session is expected_suppressed


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
        "dirty-adoption-request",
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
