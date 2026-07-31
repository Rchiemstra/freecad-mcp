"""Live FreeCAD document-observer coverage for v2 lease recovery."""

from __future__ import annotations

import os
import types
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
FreeCADGui = pytest.importorskip("FreeCADGui")

from addon.FreeCADMCP.document_lease.identity import (
    DocumentIdentityService,
    IdentityMismatchError,
    UnknownDocumentError,
    capture_file_baseline,
)
from addon.FreeCADMCP.document_lease.model import (
    LeaseOwner,
    LeaseState,
    LiveDocumentValidation,
)
from addon.FreeCADMCP.document_lease import core_authority
from addon.FreeCADMCP.document_lease.observer import (
    LeaseObserver,
    register_live_document_recovery,
)
from addon.FreeCADMCP.document_lease.service import (
    AuthorizationError,
    DocumentLeaseService,
    LocalRuntimeIdentity,
    OrphanedForeignRecoveryRequired,
    OrphanedLocalMcpRecoveryRequired,
    ProcessLivenessEvidence,
)
from addon.FreeCADMCP.document_lease.sidecar import sidecar_path_for
from addon.FreeCADMCP.document_state import document_modified_state
from addon.FreeCADMCP.rpc_server import snapshot_service


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        getattr(FreeCAD, "__mcp_test_stub__", False),
        reason="requires a real FreeCAD runtime",
    ),
]


def _owner(client: str) -> LeaseOwner:
    return LeaseOwner(
        addon_profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=os.getpid(),
        freecad_process_started_at="2026-07-29T20:00:00Z",
        boot_id="live-freecad-test",
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=os.getpid(),
        mcp_process_started_at="2026-07-29T20:00:01Z",
        hostname="localhost",
        mcp_hostname="localhost",
        client=client,
        agent_id=f"{client.lower().replace(' ', '-')}-agent",
    )


def _new_saved_box(name: str, path: Path):
    document = FreeCAD.newDocument(name)
    box = document.addObject("Part::Box", "Box")
    box.Length = 5
    box.Width = 3
    box.Height = 2
    document.recompute()
    document.saveAs(str(path))
    return document, box


def _close_if_open(name: str) -> None:
    if FreeCAD.getDocument(name) is not None:
        FreeCAD.closeDocument(name)


def test_live_unlocked_close_reopen_gets_fresh_session_identity(tmp_path):
    model = tmp_path / "UnlockedLive.FCStd"
    document, _box = _new_saved_box("UnlockedLive", model)
    identities = DocumentIdentityService()
    original = identities.register_document(document)
    service = DocumentLeaseService(identities)
    observer = LeaseObserver(service_provider=lambda: service)
    FreeCAD.addDocumentObserver(observer)

    reopened = None
    try:
        FreeCAD.closeDocument(document.Name)
        with pytest.raises(UnknownDocumentError):
            identities.resolve(original.session_uuid)

        reopened = FreeCAD.openDocument(str(model))
        fresh, imported = register_live_document_recovery(service, reopened)

        assert imported is None
        assert fresh.session_uuid != original.session_uuid
        assert (
            identities.inspect_registered_document(fresh.session_uuid, reopened)
            == fresh
        )
    finally:
        FreeCAD.removeDocumentObserver(observer)
        if reopened is not None:
            _close_if_open(reopened.Name)
        else:
            _close_if_open("UnlockedLive")


def test_live_gui_save_close_reopen_rebinds_and_allows_clean_retry(
    tmp_path,
    monkeypatch,
):
    model = tmp_path / "RecoveryLive.FCStd"
    document, box = _new_saved_box("RecoveryLive", model)
    gui_document = types.SimpleNamespace(Modified=True)
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda _name: gui_document,
        raising=False,
    )
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)

    box.Length = 17
    assert document_modified_state(document) is True
    abandoned = service.begin_dirty_adoption(
        identity.session_uuid,
        _owner("Claude"),
        task_summary="Live dirty adoption before GUI save",
        document_dirty=True,
        local_confirmation=True,
    )

    queued = []
    observer = LeaseObserver(
        service_provider=lambda: service,
        notification_queue=queued.append,
    )
    FreeCAD.addDocumentObserver(observer)
    reopened = None
    retry = None
    try:
        document.save()
        # FreeCADCmd has no real Gui::Document. Mirror the final
        # Gui::Document::save() step that runs after App::Document::save()
        # and after slotFinishSaveDocument returns.
        gui_document.Modified = False
        assert document_modified_state(document) is False
        assert len(queued) == 1
        queued.pop()()

        saved = service.get(identity.session_uuid)
        assert saved is not None
        assert saved["lease"]["state"] == LeaseState.USER_INTERVENED.value
        assert saved["document_state"]["dirty"] is False
        refreshed = identities.inspect_registered_document(
            identity.session_uuid,
            document,
        )
        assert service.identity_service.resolve(identity.session_uuid) == refreshed

        FreeCAD.closeDocument(document.Name)
        reopened = FreeCAD.openDocument(str(model))
        rebound, imported = register_live_document_recovery(service, reopened)

        assert imported is None
        assert rebound.session_uuid == identity.session_uuid
        assert identities.inspect_registered_document(
            rebound.session_uuid,
            reopened,
        ) == service.identity_service.resolve(rebound.session_uuid)
        with pytest.raises((IdentityMismatchError, ReferenceError)):
            identities.inspect_registered_document(
                rebound.session_uuid,
                document,
            )

        retry = service.begin_acquisition(
            rebound.session_uuid,
            _owner("Cursor"),
            task_summary="Retry after real FreeCAD save and reopen",
        )
        assert retry.record.state == LeaseState.ACQUIRING
        assert retry.record.generation == abandoned.record.generation + 2
        with pytest.raises(AuthorizationError):
            service.authorize(abandoned.credential)
    finally:
        if retry is not None:
            service.abort_acquisition(retry.credential)
        FreeCAD.removeDocumentObserver(observer)
        if reopened is not None:
            _close_if_open(reopened.Name)
        else:
            _close_if_open("RecoveryLive")


def test_live_core_fenced_clean_orphan_recovers_atomically(
    tmp_path,
    monkeypatch,
):
    model = tmp_path / "CoreOrphanLive.FCStd"
    document, _box = _new_saved_box("CoreOrphanLive", model)
    if not core_authority.core_owner_api_available(document):
        _close_if_open(document.Name)
        pytest.skip("requires the patched FreeCAD mutation-authority API")
    original_bytes = model.read_bytes()
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    old_owner = replace(_owner("Exited"), mcp_pid=987654)
    service = DocumentLeaseService(
        identities,
        local_runtime_identity=LocalRuntimeIdentity(
            addon_profile_id=old_owner.addon_profile_id,
            addon_runtime_id=old_owner.addon_runtime_id,
            freecad_pid=old_owner.freecad_pid,
            freecad_process_started_at=old_owner.freecad_process_started_at,
            boot_id=old_owner.boot_id,
            hostname=old_owner.hostname,
        ),
        process_liveness_probe=lambda pid: (
            ProcessLivenessEvidence(exists=False)
            if pid == old_owner.mcp_pid
            else ProcessLivenessEvidence(exists=None)
        ),
    )
    original = service.acquire(
        identity.session_uuid,
        old_owner,
        snapshot_id=str(uuid.uuid4()),
    )
    replacement_owner = replace(
        old_owner,
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=os.getpid(),
        mcp_process_started_at="2026-07-29T20:05:00Z",
        client="Replacement",
    )
    recovered = None
    snapshot_id = None
    cleanup_credential = original.credential
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    monkeypatch.setattr(snapshot_service, "_recovery_root", lambda: recovery)

    try:
        assert core_authority.set_mcp_owner(
            document,
            generation=original.record.generation,
            provider_id=old_owner.mcp_instance_id,
        )
        prior_core_status = core_authority.authority_status(document)
        assert prior_core_status is not None
        with pytest.raises(Exception):
            document.saveCopy(str(tmp_path / "denied.FCStd"))

        with pytest.raises(OrphanedLocalMcpRecoveryRequired):
            service.begin_acquisition(
                identity.session_uuid,
                replacement_owner,
            )

        baseline = capture_file_baseline(model, platform=identities.platform)
        with core_authority.open_mutation_capability(
            document,
            generation=0,
            kinds=("SaveAs",),
        ):
            snapshot_id = snapshot_service.create_lease_baseline_snapshot_gui(
                document
            )
        recovered = service.recover_orphaned_local_mcp_acquisition(
            identity.session_uuid,
            replacement_owner,
            validation=LiveDocumentValidation(
                document=identity,
                document_modified=False,
                baseline=baseline,
                baseline_validated=True,
            ),
            snapshot_id=snapshot_id,
            authority_handoff=lambda replacement: (
                core_authority.sync_mcp_owner_verified(
                    document,
                    replacement,
                )
            ),
            authority_rollback=lambda: core_authority.restore_authority_status(
                document,
                prior_core_status,
            ),
        )
        cleanup_credential = recovered.credential

        status = core_authority.authority_status(document)
        assert status is not None
        assert status["restricted"] is True
        assert status["generation"] == recovered.record.generation
        assert recovered.record.generation == original.record.generation + 1
        assert model.read_bytes() == original_bytes
        with pytest.raises(AuthorizationError):
            service.authorize(original.credential)
    finally:
        try:
            current_baseline = capture_file_baseline(
                model,
                platform=identities.platform,
            )
            service.release_clean(
                cleanup_credential,
                validation=LiveDocumentValidation(
                    document=identity,
                    document_modified=False,
                    baseline=current_baseline,
                    baseline_validated=True,
                ),
            )
        except Exception:
            pass
        core_authority.clear_owner(document)
        if snapshot_id is not None:
            snapshot_service.discard_lease_baseline_snapshot(snapshot_id)
        _close_if_open(document.Name)


def test_live_dirty_cached_worker_intervention_recovers_without_close(
    tmp_path,
    monkeypatch,
):
    model = tmp_path / "DirtyForeignOrphanLive.FCStd"
    document, box = _new_saved_box("DirtyForeignOrphanLive", model)
    gui_document = types.SimpleNamespace(Modified=True)
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda _name: gui_document,
        raising=False,
    )
    if not core_authority.core_owner_api_available(document):
        _close_if_open(document.Name)
        pytest.skip("requires the patched FreeCAD mutation-authority API")
    original_bytes = model.read_bytes()
    original_stat = model.stat()
    old_owner = replace(
        _owner("Exited"),
        freecad_pid=987653,
        mcp_pid=987654,
    )
    foreign_identities = DocumentIdentityService()
    foreign_document = foreign_identities.register(
        name=document.Name,
        path=model,
    )
    foreign_service = DocumentLeaseService(foreign_identities)
    original = foreign_service.acquire(
        foreign_document.session_uuid,
        old_owner,
        snapshot_id=str(uuid.uuid4()),
    )
    intervened = foreign_service.takeover(
        foreign_document.session_uuid,
        dirty=False,
        reason=(
            "Unscoped FreeCAD save detected: "
            "/tmp/freecad_mcp_workers/mcp_worker__legacy/"
            "snapshots/0001_DirtyForeignOrphanLive.FCStd"
        ),
    )
    intervened = foreign_service.update_local_dirty(
        intervened.document.session_uuid,
        dirty=True,
    )

    box.Length = 17
    document.recompute()
    assert document_modified_state(document) is True
    identities = DocumentIdentityService()
    local_document = identities.register_document(document)
    local_runtime = LocalRuntimeIdentity(
        addon_profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=os.getpid(),
        freecad_process_started_at="2026-07-29T20:10:00Z",
        boot_id=old_owner.boot_id,
        hostname=old_owner.hostname,
    )
    service = DocumentLeaseService(
        identities,
        local_runtime_identity=local_runtime,
        process_liveness_probe=lambda pid: (
            ProcessLivenessEvidence(exists=False)
            if pid == old_owner.freecad_pid
            else ProcessLivenessEvidence(exists=None)
        ),
    )
    service.import_adjacent_foreign_recovery(
        local_document.session_uuid,
        live_document=local_document,
    )
    sidecar = sidecar_path_for(model)
    sidecar.unlink()
    replacement_owner = replace(
        old_owner,
        addon_profile_id=local_runtime.addon_profile_id,
        addon_runtime_id=local_runtime.addon_runtime_id,
        freecad_pid=local_runtime.freecad_pid,
        freecad_process_started_at=local_runtime.freecad_process_started_at,
        boot_id=local_runtime.boot_id,
        hostname=local_runtime.hostname,
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=os.getpid(),
        mcp_process_started_at="2026-07-29T20:10:01Z",
        client="Replacement",
    )
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    monkeypatch.setattr(snapshot_service, "_recovery_root", lambda: recovery)
    snapshot_id = None
    recovered = None

    try:
        with pytest.raises(OrphanedForeignRecoveryRequired):
            service.begin_dirty_adoption(
                local_document.session_uuid,
                replacement_owner,
                document_dirty=True,
                local_confirmation=True,
            )
        baseline = capture_file_baseline(model, platform=identities.platform)
        prior_core_status = core_authority.authority_status(document)
        assert prior_core_status is not None
        with core_authority.open_mutation_capability(
            document,
            generation=0,
            kinds=("SaveAs",),
        ):
            snapshot_id = snapshot_service.create_lease_baseline_snapshot_gui(
                document,
            )
        assert document_modified_state(document) is True

        recovered = service.recover_orphaned_foreign_acquisition(
            local_document.session_uuid,
            replacement_owner,
            validation=LiveDocumentValidation(
                document=local_document,
                document_modified=True,
                baseline=baseline,
                baseline_validated=True,
            ),
            snapshot_id=snapshot_id,
            adopt_dirty=True,
            local_confirmation=True,
            authority_handoff=lambda replacement: (
                core_authority.sync_mcp_owner_verified(
                    document,
                    replacement,
                )
            ),
            authority_rollback=lambda: core_authority.restore_authority_status(
                document,
                prior_core_status,
            ),
            credential_escrow=lambda _grant: True,
        )

        status = core_authority.authority_status(document)
        assert status is not None
        assert status["restricted"] is True
        assert status["generation"] == recovered.record.generation
        assert status["provider_id"] == replacement_owner.mcp_instance_id
        assert recovered.record.state == LeaseState.LOCKED_IDLE
        assert recovered.record.dirty is True
        assert recovered.record.generation == intervened.generation + 1
        assert service.get_foreign_recovery(local_document.session_uuid) is None
        assert service.sidecar_store.read(sidecar) == recovered.record
        assert document_modified_state(document) is True
        assert model.read_bytes() == original_bytes
        final_stat = model.stat()
        assert final_stat.st_size == original_stat.st_size
        assert final_stat.st_mtime_ns == original_stat.st_mtime_ns
        with pytest.raises(AuthorizationError):
            service.authorize(original.credential)
    finally:
        if recovered is not None and sidecar.exists():
            try:
                service.sidecar_store.delete(
                    sidecar,
                    expected=recovered.record,
                )
            except Exception:
                pass
        core_authority.clear_owner(document)
        if snapshot_id is not None:
            snapshot_service.discard_lease_baseline_snapshot(snapshot_id)
        _close_if_open(document.Name)
