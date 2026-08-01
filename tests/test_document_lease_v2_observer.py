from __future__ import annotations

import sys
import types
import uuid
from dataclasses import replace
from pathlib import Path

import FreeCADGui
import pytest

from addon.FreeCADMCP import document_lock
from addon.FreeCADMCP.document_lease import observer as observer_mod
from addon.FreeCADMCP.document_lease.observer_ops.identity_registration_failure import (
    IdentityRegistrationFailure as _IdentityRegistrationFailure,
)


def test_observer_surface_exports_identity_registration_failure():
    assert observer_mod.IdentityRegistrationFailure is _IdentityRegistrationFailure
    assert "IdentityRegistrationFailure" in observer_mod.__all__


class FakeDocument:
    def __init__(self, name="Model", filename="", modified=True):
        self.Name = name
        self.FileName = filename
        self.Modified = modified


class FakeIdentity:
    def __init__(self, document: FakeDocument):
        self.session_uuid = "doc-session"
        self.name = document.Name
        self.canonical_path = document.FileName or None


class FakeIdentityService:
    def __init__(self, document: FakeDocument):
        self.document = document
        self.identity = FakeIdentity(document)

    def resolve(self, selector):
        name = selector.get("document_name")
        path = selector.get("canonical_path")
        session_uuid = selector.get("document_session_uuid")
        if name and name != self.document.Name:
            raise LookupError(name)
        if path and Path(path).resolve() != Path(self.document.FileName).resolve():
            raise LookupError(path)
        if session_uuid and session_uuid != self.identity.session_uuid:
            raise LookupError(session_uuid)
        return self.identity


class FakeService:
    def __init__(self, document: FakeDocument):
        self.identity_service = FakeIdentityService(document)
        self.current = {"state": "LOCKED_IDLE", "generation": 7}
        self.takeovers = []
        self.dirty_updates = []
        self.identity_refreshes = []
        self.sidecar_delete_calls = []

    def get(self, selector):
        if selector != "doc-session":
            raise LookupError(selector)
        return self.current

    def takeover(self, selector, *, dirty, reason):
        self.takeovers.append({"selector": selector, "dirty": dirty, "reason": reason})
        self.current = {"state": "USER_INTERVENED", "generation": 8}
        return self.current

    def update_local_dirty(self, selector, *, dirty):
        self.dirty_updates.append((selector, dirty))
        self.current = {**self.current, "dirty": dirty}
        return self.current

    def refresh_local_recovery_document_identity(self, selector, *, document):
        self.identity_refreshes.append((selector, document))
        return self.current


def make_observer(document, *, checker=lambda _key: False):
    service = FakeService(document)
    queued = []
    delivered = []
    observer = observer_mod.LeaseObserver(
        service_provider=lambda: service,
        agent_mutation_checker=checker,
        selected_document_provider=lambda: document,
        notification_callback=delivered.append,
        notification_queue=queued.append,
    )
    return observer, service, queued, delivered


def test_property_change_fences_owner_and_queues_redacted_notification(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, queued, delivered = make_observer(document)
    obj = types.SimpleNamespace(Document=document)

    result = observer.slotChangedObject(obj, "Placement")

    assert result == {"state": "USER_INTERVENED", "generation": 8}
    assert service.takeovers == [
        {
            "selector": "doc-session",
            "dirty": True,
            "reason": "Unscoped FreeCAD object property change detected: Placement",
        }
    ]
    assert delivered == []
    assert len(queued) == 1

    queued.pop()()
    assert delivered[0] == observer_mod.LeaseObserverEvent(
        kind="object property change",
        document_name="Model",
        document_session_uuid="doc-session",
        canonical_path=str(tmp_path / "Model.FCStd"),
        reason="Unscoped FreeCAD object property change detected: Placement",
        dirty=True,
        state="USER_INTERVENED",
        generation=8,
    )
    assert not hasattr(delivered[0], "token")


def test_unknown_gui_modified_state_is_fenced_as_dirty(tmp_path, monkeypatch):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"))
    del document.Modified
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda _name: None,
        raising=False,
    )
    observer, service, _queued, _delivered = make_observer(document)

    observer.slotChangedObject(types.SimpleNamespace(Document=document), "Placement")

    assert service.takeovers[0]["dirty"] is True


def test_internal_snapshot_ignores_only_its_exact_save_callbacks(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=False)
    observer, service, queued, _delivered = make_observer(document)
    snapshot = tmp_path / "worker" / "0001_Model.FCStd"
    request_id = str(uuid.uuid4())

    assert document_lock.begin_internal_snapshot_save_scope(
        request_id,
        document,
        snapshot,
    )
    try:
        assert observer.slotStartSaveDocument(document, str(snapshot)) is None
        assert observer.slotFinishSaveDocument(document, str(snapshot)) is None
        assert service.takeovers == []
        assert service.dirty_updates == []
        assert service.identity_refreshes == []
        assert queued == []

        # The narrow save marker grants no general observer attribution.
        changed = observer.slotChangedObject(
            types.SimpleNamespace(Document=document),
            "Placement",
        )
        assert changed == {"state": "USER_INTERVENED", "generation": 8}
        assert len(service.takeovers) == 1
    finally:
        assert document_lock.end_internal_snapshot_save_scope(
            request_id,
            document,
            snapshot,
        )

    assert not document_lock.is_internal_snapshot_save(document, snapshot)


@pytest.mark.parametrize("attributed_key", ["Model", "resolved-path"])
def test_agent_attribution_accepts_document_name_and_resolved_path(
    tmp_path, attributed_key
):
    filename = tmp_path / "Model.FCStd"
    document = FakeDocument("Model", str(filename), modified=True)
    resolved = str(filename.resolve())

    def checker(key):
        if attributed_key == "Model":
            return key == "Model"
        return key == resolved

    observer, service, queued, _delivered = make_observer(document, checker=checker)

    assert observer.slotCreatedObject(types.SimpleNamespace(Document=document)) is None
    assert service.takeovers == []
    assert queued == []


@pytest.mark.parametrize(
    ("callback", "args", "kind"),
    [
        (
            "slotCreatedObject",
            lambda d: (types.SimpleNamespace(Document=d),),
            "object creation",
        ),
        (
            "slotDeletedObject",
            lambda d: (types.SimpleNamespace(Document=d),),
            "object deletion",
        ),
        (
            "slotAppendDynamicProperty",
            lambda d: (types.SimpleNamespace(Document=d), "CustomLength"),
            "dynamic property addition",
        ),
        (
            "slotRemoveDynamicProperty",
            lambda d: (types.SimpleNamespace(Document=d), "CustomLength"),
            "dynamic property removal",
        ),
        (
            "slotChangePropertyEditor",
            lambda d: (types.SimpleNamespace(Document=d), "CustomLength"),
            "property editor change",
        ),
        (
            "slotBeforeAddingDynamicExtension",
            lambda d: (types.SimpleNamespace(Document=d), "App::LinkExtension"),
            "dynamic extension addition",
        ),
        (
            "slotAddedDynamicExtension",
            lambda d: (types.SimpleNamespace(Document=d), "App::LinkExtension"),
            "dynamic extension addition",
        ),
        ("slotUndoDocument", lambda d: (d,), "undo"),
        ("slotRedoDocument", lambda d: (d,), "redo"),
        ("slotBeforeRecomputeDocument", lambda d: (d,), "recompute"),
        ("slotRecomputedDocument", lambda d: (d,), "recompute"),
        ("slotOpenTransaction", lambda d: (d, "Edit sketch"), "transaction open"),
        ("slotCommitTransaction", lambda d: (d,), "transaction commit"),
        ("slotAbortTransaction", lambda d: (d,), "transaction abort"),
        ("slotStartSaveDocument", lambda d: (d, d.FileName), "save"),
        ("slotFinishSaveDocument", lambda d: (d, d.FileName), "save"),
        ("slotDeletedDocument", lambda d: (d,), "document close"),
    ],
)
def test_supported_app_callbacks_fence_unscoped_changes(tmp_path, callback, args, kind):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, queued, _delivered = make_observer(document)

    getattr(observer, callback)(*args(document))

    assert len(service.takeovers) == 1
    assert kind in service.takeovers[0]["reason"]
    assert len(queued) == (2 if callback == "slotFinishSaveDocument" else 1)


def test_finish_save_queues_clean_state_refresh_after_callback_returns(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, queued, _delivered = make_observer(document)

    observer.slotFinishSaveDocument(document, document.FileName)

    assert service.current["state"] == "USER_INTERVENED"
    assert service.dirty_updates == []
    assert len(queued) == 2

    document.Modified = False
    queued[1]()

    assert service.dirty_updates == [("doc-session", False)]
    assert service.identity_refreshes == [
        ("doc-session", document),
        ("doc-session", document),
    ]


def test_finish_save_deferred_refresh_never_takes_over_attributed_owner(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, queued, _delivered = make_observer(
        document,
        checker=lambda _key: True,
    )

    assert observer.slotFinishSaveDocument(document, document.FileName) is None
    assert len(queued) == 1

    document.Modified = False
    queued[0]()

    assert service.takeovers == []
    assert service.dirty_updates == []
    assert service.identity_refreshes == []


def test_finish_save_refreshes_registered_identity_without_lease(tmp_path):
    from addon.FreeCADMCP.document_lease.identity import DocumentIdentityService
    from addon.FreeCADMCP.document_lease.service import DocumentLeaseService

    model = tmp_path / "Unleased.FCStd"
    replacement = tmp_path / "Unleased.tmp"
    model.write_bytes(b"original archive")
    replacement.write_bytes(b"saved by the FreeCAD GUI")
    document = FakeDocument("Unleased", str(model), modified=False)
    identities = DocumentIdentityService()
    original = identities.register_document(document)
    service = DocumentLeaseService(identities)
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)

    replacement.replace(model)
    observed = identities.inspect_registered_document(
        original.session_uuid,
        document,
    )
    assert observed.file_identity != original.file_identity

    assert observer.slotFinishSaveDocument(document, document.FileName) is None

    refreshed, imported, _failure = observer_mod.register_live_document_recovery(
        service,
        document,
    )
    assert imported is None
    assert refreshed.session_uuid == original.session_uuid
    assert refreshed.file_identity == observed.file_identity
    assert service.get(refreshed.session_uuid) is None


def test_missing_foreign_sidecar_repairs_exact_proxy_identity_error(tmp_path):
    from addon.FreeCADMCP.document_lease.identity import DocumentIdentityService
    from addon.FreeCADMCP.document_lease.model import LeaseOwner
    from addon.FreeCADMCP.document_lease.service import (
        DocumentLeaseService,
        LocalRuntimeIdentity,
        ProcessLivenessEvidence,
    )
    from addon.FreeCADMCP.document_lease.sidecar import sidecar_path_for

    model = tmp_path / "StackedFault.FCStd"
    model.write_bytes(b"validated saved document")
    owner = LeaseOwner(
        addon_profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=101,
        freecad_process_started_at="2026-07-30T00:00:00Z",
        boot_id="test-boot",
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=202,
        mcp_process_started_at="2026-07-30T00:00:01Z",
        hostname="localhost",
        client="Claude",
        agent_id="claude-agent",
    )
    foreign_identities = DocumentIdentityService()
    foreign_document = foreign_identities.register(name="StackedFault", path=model)
    foreign_service = DocumentLeaseService(foreign_identities)
    foreign_service.acquire(
        foreign_document.session_uuid,
        owner,
        snapshot_id=str(uuid.uuid4()),
    )

    document = FakeDocument("StackedFault", str(model), modified=False)
    identities = DocumentIdentityService()
    local_document = identities.register_document(document)
    service = DocumentLeaseService(
        identities,
        local_runtime_identity=LocalRuntimeIdentity(
            addon_profile_id=str(uuid.uuid4()),
            addon_runtime_id=str(uuid.uuid4()),
            freecad_pid=303,
            freecad_process_started_at="2026-07-30T00:05:00Z",
            boot_id=owner.boot_id,
            hostname=owner.hostname,
        ),
        process_liveness_probe=lambda _pid: ProcessLivenessEvidence(False),
    )
    service.import_adjacent_foreign_recovery(
        local_document.session_uuid,
        live_document=local_document,
    )
    sidecar_path_for(model).unlink()

    # Reproduce the stacked in-memory fault: exact proxy/path still identify
    # the clean file, but the registry entry can no longer pass registration.
    identities._entries[local_document.session_uuid].identity = replace(
        local_document,
        file_identity=None,
    )

    repaired, imported, _failure = observer_mod.register_live_document_recovery(
        service,
        document,
    )

    assert imported is None
    assert repaired == local_document
    assert (
        identities.inspect_registered_document(
            repaired.session_uuid,
            document,
        )
        == repaired
    )
    effective = service.get_effective(repaired.session_uuid)
    assert effective["document_state"]["error"]["code"] == ("FOREIGN_SIDECAR_INVALID")
    assert "DOCUMENT_IDENTITY_ERROR" not in str(effective)


def test_missing_worker_intervention_sidecar_repairs_dirty_exact_proxy_identity(
    tmp_path,
):
    from addon.FreeCADMCP.document_lease.identity import DocumentIdentityService
    from addon.FreeCADMCP.document_lease.model import LeaseOwner, LeaseState
    from addon.FreeCADMCP.document_lease.service import (
        DocumentLeaseService,
        LocalRuntimeIdentity,
        ProcessLivenessEvidence,
    )
    from addon.FreeCADMCP.document_lease.sidecar import sidecar_path_for

    model = tmp_path / "HamaAdapter.FCStd"
    model.write_bytes(b"validated saved Hama adapter")
    owner = LeaseOwner(
        addon_profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=101,
        freecad_process_started_at="2026-07-30T00:00:00Z",
        boot_id="test-boot",
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=202,
        mcp_process_started_at="2026-07-30T00:00:01Z",
        hostname="localhost",
        client="Claude",
        agent_id="claude-agent",
    )
    foreign_identities = DocumentIdentityService()
    foreign_document = foreign_identities.register(name="HamaAdapter", path=model)
    foreign_service = DocumentLeaseService(foreign_identities)
    foreign_service.acquire(
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
    assert intervened.state == LeaseState.USER_INTERVENED
    assert intervened.validation_complete is False
    assert (
        intervened.last_verified_save_revision
        == intervened.last_mutation_revision
    )

    document = FakeDocument("HamaAdapter", str(model), modified=True)
    identities = DocumentIdentityService()
    local_document = identities.register_document(document)
    service = DocumentLeaseService(
        identities,
        local_runtime_identity=LocalRuntimeIdentity(
            addon_profile_id=str(uuid.uuid4()),
            addon_runtime_id=str(uuid.uuid4()),
            freecad_pid=303,
            freecad_process_started_at="2026-07-30T00:05:00Z",
            boot_id=owner.boot_id,
            hostname=owner.hostname,
        ),
        process_liveness_probe=lambda _pid: ProcessLivenessEvidence(False),
    )
    service.import_adjacent_foreign_recovery(
        local_document.session_uuid,
        live_document=local_document,
    )
    sidecar_path_for(model).unlink()
    identities._entries[local_document.session_uuid].identity = replace(
        local_document,
        file_identity=None,
    )

    repaired, imported, _failure = observer_mod.register_live_document_recovery(
        service,
        document,
    )

    assert imported is None
    assert repaired == local_document
    assert document.Modified is True
    assert (
        identities.inspect_registered_document(
            repaired.session_uuid,
            document,
        )
        == repaired
    )
    cached = service._foreign_records[repaired.session_uuid].persisted
    assert cached.state == LeaseState.USER_INTERVENED
    assert cached.dirty is True
    assert cached.validation_complete is False
    effective = service.get_effective(repaired.session_uuid)
    assert effective["lease"]["state"] == LeaseState.LOCKED_ERROR.value
    assert effective["document_state"]["error"]["code"] == (
        "FOREIGN_SIDECAR_INVALID"
    )
    assert effective["coordination_lost"] is True
    assert not sidecar_path_for(model).exists()


def test_gui_edit_mode_resolves_view_provider_object(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=False)
    observer, service, queued, _delivered = make_observer(document)
    gui_observer = observer_mod.LeaseGuiObserver(observer)
    view_provider = types.SimpleNamespace(
        Object=types.SimpleNamespace(Document=document)
    )

    gui_observer.slotInEdit(view_provider)

    assert service.takeovers[0]["dirty"] is False
    assert "GUI edit-mode entry" in service.takeovers[0]["reason"]
    assert len(queued) == 1


def test_close_callback_fences_without_sidecar_cleanup(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, _queued, _delivered = make_observer(document)

    observer.slotDeletedDocument(document)

    assert service.current["state"] == "USER_INTERVENED"
    assert service.sidecar_delete_calls == []


def test_unlocked_close_unregisters_identity_for_fresh_reopen(tmp_path):
    from addon.FreeCADMCP.document_lease.identity import (
        DocumentIdentityService,
        UnknownDocumentError,
    )
    from addon.FreeCADMCP.document_lease.service import DocumentLeaseService

    model = tmp_path / "Unlocked.FCStd"
    model.write_bytes(b"saved document")
    closed = FakeDocument("Unlocked", str(model), modified=False)
    identities = DocumentIdentityService()
    original = identities.register_document(closed)
    service = DocumentLeaseService(identities)
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)

    assert observer.slotDeletedDocument(closed) is None
    with pytest.raises(UnknownDocumentError):
        identities.resolve(original.session_uuid)

    reopened = FakeDocument("Unlocked", str(model), modified=False)
    fresh, imported, _failure = observer_mod.register_live_document_recovery(
        service,
        reopened,
    )

    assert imported is None
    assert fresh.session_uuid != original.session_uuid
    assert (
        identities.inspect_registered_document(
            fresh.session_uuid,
            reopened,
        )
        == fresh
    )


def test_close_reopen_rebinds_unreturned_reservation_then_allows_retry(tmp_path):
    from addon.FreeCADMCP.document_lease.identity import (
        DocumentIdentityService,
        IdentityMismatchError,
    )
    from addon.FreeCADMCP.document_lease.model import LeaseOwner, LeaseState
    from addon.FreeCADMCP.document_lease.service import DocumentLeaseService

    model = tmp_path / "Reopened.FCStd"
    model.write_bytes(b"saved document")
    closed = FakeDocument("Reopened", str(model), modified=False)
    identities = DocumentIdentityService()
    original = identities.register_document(closed)
    service = DocumentLeaseService(identities)

    def owner(client):
        return LeaseOwner(
            addon_profile_id=str(uuid.uuid4()),
            addon_runtime_id=str(uuid.uuid4()),
            freecad_pid=101,
            freecad_process_started_at="2026-07-29T20:00:00Z",
            boot_id="test-boot",
            mcp_instance_id=str(uuid.uuid4()),
            mcp_pid=202,
            mcp_process_started_at="2026-07-29T20:00:01Z",
            hostname="localhost",
            client=client,
            agent_id=f"{client}-agent",
        )

    abandoned = service.begin_acquisition(
        original.session_uuid,
        owner("Claude"),
    )
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)
    closed_record = observer.slotDeletedDocument(closed)
    assert closed_record.state == LeaseState.USER_INTERVENED

    reopened = FakeDocument("Reopened", str(model), modified=False)
    rebound, imported, _failure = observer_mod.register_live_document_recovery(
        service,
        reopened,
    )

    assert imported is None
    assert rebound == closed_record.document
    assert rebound.session_uuid == original.session_uuid
    assert (
        identities.inspect_registered_document(
            rebound.session_uuid,
            reopened,
        )
        == rebound
    )
    with pytest.raises(IdentityMismatchError):
        identities.inspect_registered_document(rebound.session_uuid, closed)

    retry = service.begin_acquisition(
        rebound.session_uuid,
        owner("Cursor"),
    )
    assert retry.record.state == LeaseState.ACQUIRING
    assert retry.record.generation == abandoned.record.generation + 2


def test_save_start_then_close_refreshes_identity_without_finish_callback(tmp_path):
    from addon.FreeCADMCP.document_lease.identity import DocumentIdentityService
    from addon.FreeCADMCP.document_lease.model import LeaseOwner, LeaseState
    from addon.FreeCADMCP.document_lease.service import DocumentLeaseService

    model = tmp_path / "CloseAfterSave.FCStd"
    replacement = tmp_path / "saved.FCStd"
    model.write_bytes(b"saved baseline")
    replacement.write_bytes(b"user GUI save")
    closed = FakeDocument("CloseAfterSave", str(model), modified=True)
    identities = DocumentIdentityService()
    original = identities.register_document(closed)
    service = DocumentLeaseService(identities)
    service.begin_dirty_adoption(
        original.session_uuid,
        LeaseOwner(
            addon_profile_id=str(uuid.uuid4()),
            addon_runtime_id=str(uuid.uuid4()),
            freecad_pid=101,
            freecad_process_started_at="2026-07-29T20:00:00Z",
            boot_id="test-boot",
            mcp_instance_id=str(uuid.uuid4()),
            mcp_pid=202,
            mcp_process_started_at="2026-07-29T20:00:01Z",
            hostname="localhost",
            client="Claude",
            agent_id="claude-agent",
        ),
        document_dirty=True,
        local_confirmation=True,
    )
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)

    observer.slotStartSaveDocument(closed, closed.FileName)
    model.unlink()
    replacement.replace(model)
    closed.Modified = False
    closed_record = observer.slotDeletedDocument(closed)

    assert closed_record.state == LeaseState.USER_INTERVENED
    assert closed_record.document.file_identity != original.file_identity
    reopened = FakeDocument("CloseAfterSave", str(model), modified=False)
    rebound, imported, _failure = observer_mod.register_live_document_recovery(
        service,
        reopened,
    )
    assert imported is None
    assert rebound == closed_record.document


def test_deferred_save_refresh_ignores_closed_proxy_after_reopen(tmp_path):
    from addon.FreeCADMCP.document_lease.identity import DocumentIdentityService
    from addon.FreeCADMCP.document_lease.model import LeaseOwner
    from addon.FreeCADMCP.document_lease.service import DocumentLeaseService

    model = tmp_path / "DeferredAfterReopen.FCStd"
    model.write_bytes(b"saved baseline")
    closed = FakeDocument("DeferredAfterReopen", str(model), modified=True)
    identities = DocumentIdentityService()
    identity = identities.register_document(closed)
    service = DocumentLeaseService(identities)
    service.begin_dirty_adoption(
        identity.session_uuid,
        LeaseOwner(
            addon_profile_id=str(uuid.uuid4()),
            addon_runtime_id=str(uuid.uuid4()),
            freecad_pid=101,
            freecad_process_started_at="2026-07-29T20:00:00Z",
            boot_id="test-boot",
            mcp_instance_id=str(uuid.uuid4()),
            mcp_pid=202,
            mcp_process_started_at="2026-07-29T20:00:01Z",
            hostname="localhost",
            client="Claude",
            agent_id="claude-agent",
        ),
        document_dirty=True,
        local_confirmation=True,
    )
    queued = []
    observer = observer_mod.LeaseObserver(
        service_provider=lambda: service,
        notification_queue=queued.append,
    )

    observer.slotFinishSaveDocument(closed, closed.FileName)
    assert len(queued) == 1
    closed.Modified = False
    observer.slotDeletedDocument(closed)
    reopened = FakeDocument("DeferredAfterReopen", str(model), modified=False)
    rebound, imported, _failure = observer_mod.register_live_document_recovery(
        service,
        reopened,
    )
    assert imported is None
    assert rebound is not None

    reopened.Modified = True
    observer.slotChangedDocument(reopened, "Touched")
    assert service.get(identity.session_uuid)["document_state"]["dirty"] is True

    queued[0]()

    assert service.get(identity.session_uuid)["document_state"]["dirty"] is True


def test_stale_closed_proxy_callback_cannot_fence_reopened_owner(tmp_path):
    from addon.FreeCADMCP.document_lease.identity import DocumentIdentityService
    from addon.FreeCADMCP.document_lease.model import LeaseOwner, LeaseState
    from addon.FreeCADMCP.document_lease.service import DocumentLeaseService

    model = tmp_path / "StaleProxy.FCStd"
    model.write_bytes(b"saved baseline")
    closed = FakeDocument("StaleProxy", str(model), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(closed)
    service = DocumentLeaseService(identities)

    def owner(client):
        return LeaseOwner(
            addon_profile_id=str(uuid.uuid4()),
            addon_runtime_id=str(uuid.uuid4()),
            freecad_pid=101,
            freecad_process_started_at="2026-07-29T20:00:00Z",
            boot_id="test-boot",
            mcp_instance_id=str(uuid.uuid4()),
            mcp_pid=202,
            mcp_process_started_at="2026-07-29T20:00:01Z",
            hostname="localhost",
            client=client,
            agent_id=f"{client}-agent",
        )

    service.begin_acquisition(identity.session_uuid, owner("Claude"))
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)
    observer.slotDeletedDocument(closed)
    reopened = FakeDocument("StaleProxy", str(model), modified=False)
    rebound, imported, _failure = observer_mod.register_live_document_recovery(
        service,
        reopened,
    )
    assert imported is None
    replacement = service.begin_acquisition(
        rebound.session_uuid,
        owner("Cursor"),
    )

    closed.Modified = True
    assert observer.slotChangedDocument(closed, "LateCallback") is None

    assert (
        service.authorize(
            replacement.credential,
            allowed_states={LeaseState.ACQUIRING},
        ).state
        == LeaseState.ACQUIRING
    )


def test_close_reopen_rebinds_promoted_lease_but_keeps_recovery_block(tmp_path):
    from addon.FreeCADMCP.document_lease.identity import DocumentIdentityService
    from addon.FreeCADMCP.document_lease.model import LeaseOwner
    from addon.FreeCADMCP.document_lease.service import (
        DocumentLeaseService,
        LeaseConflictError,
    )

    model = tmp_path / "PromotedReopen.FCStd"
    model.write_bytes(b"saved document")
    closed = FakeDocument("PromotedReopen", str(model), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(closed)

    def owner(client):
        return LeaseOwner(
            addon_profile_id=str(uuid.uuid4()),
            addon_runtime_id=str(uuid.uuid4()),
            freecad_pid=101,
            freecad_process_started_at="2026-07-29T20:00:00Z",
            boot_id="test-boot",
            mcp_instance_id=str(uuid.uuid4()),
            mcp_pid=202,
            mcp_process_started_at="2026-07-29T20:00:01Z",
            hostname="localhost",
            client=client,
            agent_id=f"{client}-agent",
        )

    service = DocumentLeaseService(identities)
    service.acquire(
        identity.session_uuid,
        owner("Claude"),
        snapshot_id=str(uuid.uuid4()),
    )
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)
    observer.slotDeletedDocument(closed)
    reopened = FakeDocument("PromotedReopen", str(model), modified=False)

    rebound, imported, _failure = observer_mod.register_live_document_recovery(
        service,
        reopened,
    )

    assert imported is None
    assert rebound.session_uuid == identity.session_uuid
    with pytest.raises(LeaseConflictError, match="already has a lease"):
        service.begin_acquisition(
            rebound.session_uuid,
            owner("Cursor"),
        )


def test_close_reopen_refuses_changed_file_identity(tmp_path):
    from addon.FreeCADMCP.document_lease.identity import DocumentIdentityService
    from addon.FreeCADMCP.document_lease.model import LeaseOwner
    from addon.FreeCADMCP.document_lease.service import DocumentLeaseService

    model = tmp_path / "Changed.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    model.write_bytes(b"saved document")
    replacement.write_bytes(b"unexpected replacement")
    closed = FakeDocument("Changed", str(model), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(closed)
    service = DocumentLeaseService(identities)
    owner = LeaseOwner(
        addon_profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=101,
        freecad_process_started_at="2026-07-29T20:00:00Z",
        boot_id="test-boot",
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=202,
        mcp_process_started_at="2026-07-29T20:00:01Z",
        hostname="localhost",
        client="Claude",
        agent_id="claude-agent",
    )
    service.begin_acquisition(identity.session_uuid, owner)
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)
    observer.slotDeletedDocument(closed)
    model.unlink()
    replacement.replace(model)

    reopened = FakeDocument("Changed", str(model), modified=False)
    rebound, imported, _failure = observer_mod.register_live_document_recovery(
        service,
        reopened,
    )

    assert rebound is None
    assert imported is None
    assert identities.resolve(identity.session_uuid) == identity
    assert (
        identities.inspect_registered_document(
            identity.session_uuid,
            closed,
        ).file_identity
        != identity.file_identity
    )


def test_close_reopen_preserves_foreign_recovery_then_dead_owner_retry(tmp_path):
    from addon.FreeCADMCP.document_lease.identity import DocumentIdentityService
    from addon.FreeCADMCP.document_lease.model import LeaseOwner, LeaseState
    from addon.FreeCADMCP.document_lease.service import (
        DocumentLeaseService,
        LocalRuntimeIdentity,
        ProcessLivenessEvidence,
    )

    model = tmp_path / "ForeignReopen.FCStd"
    model.write_bytes(b"saved document")
    owner = LeaseOwner(
        addon_profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=101,
        freecad_process_started_at="2026-07-29T20:00:00Z",
        boot_id="test-boot",
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=202,
        mcp_process_started_at="2026-07-29T20:00:01Z",
        hostname="localhost",
        client="Claude",
        agent_id="claude-agent",
    )
    foreign_identities = DocumentIdentityService()
    foreign_document = foreign_identities.register(name="ForeignReopen", path=model)
    foreign_service = DocumentLeaseService(foreign_identities)
    abandoned = foreign_service.begin_acquisition(
        foreign_document.session_uuid,
        owner,
    )

    closed = FakeDocument("ForeignReopen", str(model), modified=False)
    local_identities = DocumentIdentityService()
    local_document = local_identities.register_document(closed)
    restarted = DocumentLeaseService(
        local_identities,
        local_runtime_identity=LocalRuntimeIdentity(
            addon_profile_id=str(uuid.uuid4()),
            addon_runtime_id=str(uuid.uuid4()),
            freecad_pid=303,
            freecad_process_started_at="2026-07-29T20:05:00Z",
            boot_id=owner.boot_id,
            hostname=owner.hostname,
        ),
        process_liveness_probe=lambda _pid: ProcessLivenessEvidence(False),
    )
    restarted.import_adjacent_foreign_recovery(
        local_document.session_uuid,
        live_document=local_document,
    )
    observer = observer_mod.LeaseObserver(service_provider=lambda: restarted)

    closed_status = observer.slotDeletedDocument(closed)
    assert closed_status["source"] == "foreign_recovery"

    reopened = FakeDocument("ForeignReopen", str(model), modified=False)
    rebound, imported, _failure = observer_mod.register_live_document_recovery(
        restarted,
        reopened,
    )
    assert imported is None
    assert rebound == local_document
    retry = restarted.begin_acquisition(
        rebound.session_uuid,
        LeaseOwner(
            addon_profile_id=str(uuid.uuid4()),
            addon_runtime_id=str(uuid.uuid4()),
            freecad_pid=303,
            freecad_process_started_at="2026-07-29T20:05:00Z",
            boot_id=owner.boot_id,
            mcp_instance_id=str(uuid.uuid4()),
            mcp_pid=404,
            mcp_process_started_at="2026-07-29T20:05:01Z",
            hostname=owner.hostname,
            client="GPT Sol",
            agent_id="gpt-sol-agent",
        ),
    )

    assert retry.record.state == LeaseState.ACQUIRING
    assert retry.record.generation == abandoned.record.generation + 1


def test_repeated_callbacks_do_not_repeat_takeover_for_intervened_state(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, queued, _delivered = make_observer(document)
    obj = types.SimpleNamespace(Document=document)

    observer.slotBeforeChangeObject(obj, "Length")
    observer.slotChangedObject(obj, "Length")
    observer.slotRecomputedDocument(document)

    assert len(service.takeovers) == 1
    assert len(queued) == 1


def test_intervened_document_observer_refreshes_dirty_without_new_takeover(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, queued, _delivered = make_observer(document)
    observer.take_over_selected_document(reason="Confirmed")
    document.Modified = False

    result = observer.slotFinishSaveDocument(document, document.FileName)

    assert result["state"] == "USER_INTERVENED"
    assert result["dirty"] is False
    assert service.dirty_updates[-1] == ("doc-session", False)
    assert service.identity_refreshes == [("doc-session", document)]
    assert len(service.takeovers) == 1
    assert len(queued) == 1


@pytest.mark.parametrize(
    "callback_order",
    ["finish-only", "start-and-finish"],
)
def test_gui_save_refreshes_identity_and_clean_retry_fences_lost_reservation(
    tmp_path,
    callback_order,
):
    from addon.FreeCADMCP.document_lease.identity import DocumentIdentityService
    from addon.FreeCADMCP.document_lease.model import LeaseOwner, LeaseState
    from addon.FreeCADMCP.document_lease.service import (
        AuthorizationError,
        DocumentLeaseService,
    )

    model = tmp_path / "Model.FCStd"
    replacement = tmp_path / "saved.FCStd"
    model.write_bytes(b"saved baseline")
    replacement.write_bytes(b"user GUI save")
    document = FakeDocument("Model", str(model), modified=True)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)

    def owner(client):
        return LeaseOwner(
            addon_profile_id=str(uuid.uuid4()),
            addon_runtime_id=str(uuid.uuid4()),
            freecad_pid=101,
            freecad_process_started_at="2026-07-29T20:00:00Z",
            boot_id="test-boot",
            mcp_instance_id=str(uuid.uuid4()),
            mcp_pid=202,
            mcp_process_started_at="2026-07-29T20:00:01Z",
            hostname="localhost",
            client=client,
            agent_id=f"{client}-agent",
        )

    abandoned = service.begin_dirty_adoption(
        identity.session_uuid,
        owner("Claude"),
        document_dirty=True,
        local_confirmation=True,
    )
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)

    if callback_order == "start-and-finish":
        started = observer.slotStartSaveDocument(document, document.FileName)
        assert started.state == LeaseState.USER_INTERVENED
    model.unlink()
    replacement.replace(model)
    document.Modified = False

    finished = observer.slotFinishSaveDocument(document, document.FileName)

    assert finished.state == LeaseState.USER_INTERVENED
    assert finished.dirty is False
    assert finished.document.file_identity != identity.file_identity
    assert identities.register_document(document) == finished.document

    retry = service.begin_acquisition(
        finished.document.session_uuid,
        owner("GPT Sol"),
        task_summary="Retry after GUI save",
    )
    assert retry.record.state == LeaseState.ACQUIRING
    assert retry.record.generation == abandoned.record.generation + 2
    with pytest.raises(AuthorizationError):
        service.authorize(abandoned.credential)


def test_manual_takeover_uses_selected_document_even_during_agent_context(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, _queued, _delivered = make_observer(
        document, checker=lambda _key: True
    )

    observer.take_over_selected_document(reason="Confirmed by local user")

    assert len(service.takeovers) == 1
    assert "manual takeover" in service.takeovers[0]["reason"]
    assert "Confirmed by local user" in service.takeovers[0]["reason"]


def test_created_document_freshly_registers_and_imports_adjacent_v2(tmp_path):
    model = tmp_path / "Recovered.FCStd"
    model.write_bytes(b"archive")
    sidecar = Path(f"{model}.freecad-mcp.lock")
    sidecar.write_bytes(b"opaque-valid-record-owned-by-service")
    document = FakeDocument("Recovered", str(model), modified=True)
    identity = types.SimpleNamespace(
        session_uuid="local-session",
        name="Recovered",
        canonical_path=str(model),
    )
    calls = []

    class Identities:
        @staticmethod
        def register_document(exact):
            assert exact is document
            calls.append("register")
            return identity

        @staticmethod
        def inspect_registered_document(session_uuid, exact):
            assert session_uuid == "local-session"
            assert exact is document
            calls.append("inspect")
            return identity

    class Service:
        identity_service = Identities()

        @staticmethod
        def get(_selector):
            return None

        @staticmethod
        def get_foreign_recovery(_selector):
            return None

        @staticmethod
        def import_adjacent_foreign_recovery(selector, *, live_document):
            calls.append(("import", selector, live_document))
            return {
                "generation": 4,
                "lease": {"state": "STALE"},
                "source": "foreign_recovery",
            }

    queued = []
    delivered = []
    observer = observer_mod.LeaseObserver(
        service_provider=lambda: Service(),
        notification_callback=delivered.append,
        notification_queue=queued.append,
    )

    result = observer.slotCreatedDocument(document)

    assert result["source"] == "foreign_recovery"
    assert calls == [
        "register",
        "inspect",
        ("import", "local-session", identity),
    ]
    assert len(queued) == 1
    queued[0]()
    assert delivered[0].state == "STALE"
    assert delivered[0].document_session_uuid == "local-session"


def test_created_document_defers_identity_until_open_path_is_attached():
    document = FakeDocument("Opening", filename="", modified=False)

    class Identities:
        @staticmethod
        def register_document(_document):
            raise AssertionError("provisional unsaved identity was registered")

    service = types.SimpleNamespace(identity_service=Identities())
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)

    assert observer.slotCreatedDocument(document) is None


def test_created_document_never_clears_or_recovers_invalid_sidecar(tmp_path):
    model = tmp_path / "Malformed.FCStd"
    model.write_bytes(b"archive")
    sidecar = Path(f"{model}.freecad-mcp.lock")
    original = b"malformed authority"
    sidecar.write_bytes(original)
    document = FakeDocument("Malformed", str(model), modified=False)
    identity = types.SimpleNamespace(
        session_uuid="local-session",
        name="Malformed",
        canonical_path=str(model),
    )

    class Identities:
        register_document = staticmethod(lambda _document: identity)
        inspect_registered_document = staticmethod(
            lambda _session_uuid, _document: identity
        )

    service = types.SimpleNamespace(
        identity_service=Identities(),
        get=lambda _selector: None,
        get_foreign_recovery=lambda _selector: None,
        import_adjacent_foreign_recovery=lambda *_args, **_kwargs: (
            _ for _ in ()
        ).throw(ValueError("invalid schema")),
    )
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)

    assert observer.slotCreatedDocument(document) is None
    assert sidecar.read_bytes() == original


def test_missing_or_failing_runtime_service_is_safe(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    no_service = observer_mod.LeaseObserver(service_provider=lambda: None)
    bad_service = observer_mod.LeaseObserver(
        service_provider=lambda: (_ for _ in ()).throw(RuntimeError("offline"))
    )

    assert no_service.slotRecomputedDocument(document) is None
    assert bad_service.slotRecomputedDocument(document) is None


def test_default_service_lookup_uses_loaded_module_without_import(monkeypatch):
    service = object()
    module = types.SimpleNamespace(document_lease_service=service)
    monkeypatch.setitem(sys.modules, "rpc_server.rpc_server", module)

    assert observer_mod.get_runtime_service() is service


class FakeObserverModule:
    def __init__(self):
        self.added = []
        self.removed = []

    def addDocumentObserver(self, value):
        self.added.append(value)

    def removeDocumentObserver(self, value):
        self.removed.append(value)


def test_registration_and_unregistration_are_idempotent():
    observer_mod.unregister_observer()
    app = FakeObserverModule()
    gui = FakeObserverModule()
    try:
        first = observer_mod.register_observer(
            freecad_module=app,
            freecad_gui_module=gui,
            service_provider=lambda: None,
        )
        second = observer_mod.register_observer(
            freecad_module=app,
            freecad_gui_module=gui,
            service_provider=lambda: None,
        )

        assert first is second
        assert app.added == [first]
        assert len(gui.added) == 1
        assert app._mcp_document_lease_observer is first
    finally:
        observer_mod.unregister_observer()

    assert app.removed == [first]
    assert gui.removed == gui.added
    assert not hasattr(app, "_mcp_document_lease_observer")
    assert not hasattr(gui, "_mcp_document_lease_gui_observer")


def test_notification_queue_failure_does_not_deliver_synchronously(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    service = FakeService(document)
    delivered = []
    observer = observer_mod.LeaseObserver(
        service_provider=lambda: service,
        notification_callback=delivered.append,
        notification_queue=lambda _callback: (_ for _ in ()).throw(
            RuntimeError("Qt stopped")
        ),
    )

    observer.slotRecomputedDocument(document)

    assert service.current["state"] == "USER_INTERVENED"
    assert delivered == []


def test_register_live_document_recovery_skips_name_resolve_mismatch():
    """Registration failure must not resolve-by-name into a foreign proxy."""

    from addon.FreeCADMCP.document_lease.identity import (
        DocumentIdentityService,
        DuplicateDocumentError,
    )

    identities = DocumentIdentityService()
    first = FakeDocument("Model", filename=r"C:\tmp\Model.FCStd")
    second = FakeDocument("Model", filename=r"C:\tmp\Model.FCStd")
    identities.register_document(first)

    class _Service:
        identity_service = identities

        def get(self, _session):
            return None

    # Same name, different proxy object → register raises; recovery must skip
    # quietly instead of inspect-mismatch warning spam.
    with pytest.raises(DuplicateDocumentError):
        identities.register_document(second)

    identity, imported, _failure = observer_mod.register_live_document_recovery(
        _Service(), second
    )
    assert identity is None
    assert imported is None
