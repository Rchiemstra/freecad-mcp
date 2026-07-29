"""Live FreeCAD document-observer coverage for v2 lease recovery."""

from __future__ import annotations

import os
import types
import uuid
from pathlib import Path

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
FreeCADGui = pytest.importorskip("FreeCADGui")

from addon.FreeCADMCP.document_lease.identity import (
    DocumentIdentityService,
    IdentityMismatchError,
    UnknownDocumentError,
)
from addon.FreeCADMCP.document_lease.model import LeaseOwner, LeaseState
from addon.FreeCADMCP.document_lease.observer import (
    LeaseObserver,
    register_live_document_recovery,
)
from addon.FreeCADMCP.document_lease.service import (
    AuthorizationError,
    DocumentLeaseService,
)
from addon.FreeCADMCP.document_state import document_modified_state


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
