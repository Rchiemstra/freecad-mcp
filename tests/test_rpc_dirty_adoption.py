"""Focused RPC tests for initial dirty-document lease adoption."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.document_lease import (
    DocumentIdentityService,
    DocumentLeaseService,
    LeaseOwner,
    LeaseState,
    LocalRuntimeIdentity,
    SidecarStore,
    sidecar_path_for,
)
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
    assert (
        "document_name, document_session_uuid, and canonical_path"
        in result["error"]
    )
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
