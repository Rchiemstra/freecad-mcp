"""Focused RPC tests for dirty exact-owner stale reconciliation (P4 / D5)."""

from __future__ import annotations

import os
import threading
import uuid
from dataclasses import replace

import pytest

from addon.FreeCADMCP import document_lease as lease_core
from addon.FreeCADMCP.document_lock import (
    reset_registry_for_tests,
    set_request_identity,
)
from addon.FreeCADMCP.document_lease import (
    DocumentIdentityService,
    DocumentLeaseService,
    LeaseOwner,
    LeaseState,
    SidecarStore,
)
from addon.FreeCADMCP.rpc_server import rpc_server as addon_rpc
from addon.FreeCADMCP.rpc_server import snapshot_service


class _Document:
    def __init__(self, name: str, path: str = "", *, modified: bool = False) -> None:
        self.Name = name
        self.Label = name
        self.FileName = path
        self.Modified = modified


class _TrackedGuiDispatch:
    def __init__(
        self, events: list[str] | None = None, *, after_first=None
    ) -> None:
        self.events = events if events is not None else []
        self.after_first = after_first
        self.in_gui = False
        self.calls = 0
        self.gui_thread_ids: list[int] = []

    def __call__(self, task, timeout=None):
        del timeout
        self.calls += 1
        call_number = self.calls
        result = []
        failure = []

        def run():
            self.gui_thread_ids.append(threading.get_ident())
            self.events.append(f"gui-enter-{call_number}")
            self.in_gui = True
            try:
                result.append(task())
            except BaseException as exc:
                failure.append(exc)
            finally:
                self.in_gui = False
                self.events.append(f"gui-exit-{call_number}")

        thread = threading.Thread(target=run, name="mock-freecad-gui")
        thread.start()
        thread.join()
        if failure:
            raise failure[0]
        if self.calls == 1 and self.after_first is not None:
            self.after_first()
        return result[0]


def _owner() -> LeaseOwner:
    return LeaseOwner(
        addon_profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=123,
        freecad_process_started_at="2026-07-22T00:00:00Z",
        boot_id="test-boot",
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=456,
        mcp_process_started_at="2026-07-22T00:00:01Z",
        hostname="test-host",
        client="dirty-stale-reconcile-test",
        agent_id="agent-a",
    )


def _wire_from_grant(grant) -> dict[str, object]:
    return {
        "lease_id": grant.credential.lease_id,
        "document_session_uuid": grant.credential.document_session_uuid,
        "generation": grant.credential.generation,
        "token": grant.credential.token,
    }


def _install_rpc_runtime(
    monkeypatch,
    *,
    document,
    identities: DocumentIdentityService,
    service: DocumentLeaseService,
    owner: LeaseOwner,
    wire: dict[str, object],
) -> tuple[addon_rpc.FreeCADRPC, _TrackedGuiDispatch]:
    documents = {document.Name: document}
    monkeypatch.setattr(addon_rpc, "document_identity_service", identities)
    monkeypatch.setattr(addon_rpc, "document_lease_service", service)
    monkeypatch.setattr(addon_rpc.FreeCAD, "getDocument", documents.get)
    monkeypatch.setattr(
        addon_rpc.FreeCAD, "listDocuments", lambda: dict(documents)
    )
    set_request_identity(
        instance_id=owner.mcp_instance_id,
        authenticated_session_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
    )
    dispatch = _TrackedGuiDispatch()
    rpc = addon_rpc.FreeCADRPC()
    rpc._dispatch_gui = dispatch
    return rpc, dispatch


@pytest.fixture(autouse=True)
def _clean_request_identity():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


@pytest.fixture
def recovery_snapshot_root(tmp_path, monkeypatch):
    monkeypatch.setattr(
        snapshot_service.FreeCAD,
        "getUserAppDataDir",
        lambda: str(tmp_path),
        raising=False,
    )
    monkeypatch.setattr(
        snapshot_service, "_harden_directory_permissions", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        snapshot_service, "_harden_permissions", lambda *_args, **_kwargs: None
    )
    return tmp_path


def _install_saved_dirty_stale(tmp_path, monkeypatch):
    model = tmp_path / "dirty-saved-stale.FCStd"
    model.write_bytes(b"stable-baseline-payload")
    document = _Document("DirtySavedStale", str(model), modified=True)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    owner = _owner()
    service = DocumentLeaseService(
        identities,
        SidecarStore(network_detector=lambda _path: False),
    )
    grant = service.acquire(
        identity.session_uuid,
        owner,
        snapshot_id=str(uuid.uuid4()),
    )
    service.begin_mutation(grant.credential, operation="probe")
    service.complete_operation(grant.credential, dirty=True)
    stale = service.mark_stale(identity.session_uuid)
    assert stale.dirty is True
    assert stale.last_verified_save_revision < stale.last_mutation_revision
    assert stale.validation_complete is False
    wire = _wire_from_grant(grant)
    return model, document, identities, service, stale, wire, owner


def _install_never_saved_dirty_stale(recovery_snapshot_root, monkeypatch):
    document = _Document("NeverSavedDirty", "", modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    owner = _owner()
    service = DocumentLeaseService(
        identities,
        SidecarStore(network_detector=lambda _path: False),
    )
    reservation = service.begin_acquisition(
        identity.session_uuid,
        owner,
        document_dirty=False,
    )
    snapshot_id = str(uuid.uuid4())
    snapshot_service.recovery_snapshot_path(snapshot_id).write_bytes(b"recovery")
    grant = service.complete_acquisition(
        reservation.credential,
        baseline=None,
        baseline_validated=False,
        snapshot_id=snapshot_id,
    )
    service.begin_mutation(grant.credential, operation="edit")
    service.complete_operation(grant.credential, dirty=True)
    document.Modified = True
    stale = service.mark_stale(identity.session_uuid)
    assert stale.baseline is None
    assert stale.document.canonical_path is None
    assert stale.dirty is True
    assert stale.last_mutation_revision >= 1
    wire = _wire_from_grant(grant)
    return document, identities, service, stale, wire, owner, snapshot_id


@pytest.mark.unit
def test_saved_dirty_stale_reconcile_without_post_mutation_save(
    tmp_path, monkeypatch
):
    model, document, identities, service, _stale, wire, owner = (
        _install_saved_dirty_stale(tmp_path, monkeypatch)
    )
    rpc, dispatch = _install_rpc_runtime(
        monkeypatch,
        document=document,
        identities=identities,
        service=service,
        owner=owner,
        wire=wire,
    )

    result = rpc.lease_reconcile(wire)

    assert result["success"] is True
    assert result["lease"]["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["lease"]["document_state"]["dirty"] is True
    assert service.get(wire["document_session_uuid"])["lease"]["state"] == (
        LeaseState.LOCKED_IDLE.value
    )
    assert dispatch.calls == 2
    assert model.read_bytes() == b"stable-baseline-payload"


@pytest.mark.unit
def test_never_saved_dirty_stale_reconcile_uses_in_memory_continuity(
    recovery_snapshot_root, monkeypatch
):
    document, identities, service, _stale, wire, owner, snapshot_id = (
        _install_never_saved_dirty_stale(recovery_snapshot_root, monkeypatch)
    )
    events: list[str] = []
    dispatch = _TrackedGuiDispatch(events)
    rpc, _ = _install_rpc_runtime(
        monkeypatch,
        document=document,
        identities=identities,
        service=service,
        owner=owner,
        wire=wire,
    )
    rpc._dispatch_gui = dispatch

    def unexpected_capture(*_args, **_kwargs):
        raise AssertionError("never-saved stale reconcile must not hash disk")

    monkeypatch.setattr(lease_core, "capture_file_baseline", unexpected_capture)

    result = rpc.lease_reconcile(wire)

    assert result["success"] is True
    assert result["lease"]["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["lease"]["document_state"]["dirty"] is True
    assert result["lease"]["document_state"]["snapshot_id"] == snapshot_id
    assert dispatch.calls == 2
    assert "full-sha-capture" not in events


@pytest.mark.unit
def test_never_saved_stale_reconcile_refuses_missing_recovery_snapshot(
    recovery_snapshot_root, monkeypatch
):
    document, identities, service, stale, wire, owner, snapshot_id = (
        _install_never_saved_dirty_stale(recovery_snapshot_root, monkeypatch)
    )
    snapshot_service.recovery_snapshot_path(snapshot_id).unlink()
    rpc, _ = _install_rpc_runtime(
        monkeypatch,
        document=document,
        identities=identities,
        service=service,
        owner=owner,
        wire=wire,
    )

    result = rpc.lease_reconcile(wire)

    assert result["success"] is False
    assert result["error_code"] == "LIVE_DOCUMENT_VALIDATION_FAILED"
    assert "intact recovery snapshot" in result["error"]
    assert service.get(wire["document_session_uuid"])["lease"]["state"] == (
        LeaseState.STALE.value
    )


@pytest.mark.unit
def test_never_saved_stale_reconcile_refuses_clean_live_document(
    recovery_snapshot_root, monkeypatch
):
    document, identities, service, _stale, wire, owner, _snapshot_id = (
        _install_never_saved_dirty_stale(recovery_snapshot_root, monkeypatch)
    )
    document.Modified = False
    rpc, _ = _install_rpc_runtime(
        monkeypatch,
        document=document,
        identities=identities,
        service=service,
        owner=owner,
        wire=wire,
    )

    result = rpc.lease_reconcile(wire)

    assert result["success"] is False
    assert result["error_code"] == "LIVE_DOCUMENT_VALIDATION_FAILED"
    assert service.get(wire["document_session_uuid"])["lease"]["state"] == (
        LeaseState.STALE.value
    )


@pytest.mark.unit
def test_reconcile_is_idempotent_after_success(tmp_path, monkeypatch):
    model, document, identities, service, _stale, wire, owner = (
        _install_saved_dirty_stale(tmp_path, monkeypatch)
    )
    rpc, dispatch = _install_rpc_runtime(
        monkeypatch,
        document=document,
        identities=identities,
        service=service,
        owner=owner,
        wire=wire,
    )

    first = rpc.lease_reconcile(wire)
    second = rpc.lease_reconcile(wire)

    assert first["success"] is True
    assert second["success"] is True
    assert second["lease"]["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert dispatch.calls == 3
    assert model.exists()


@pytest.mark.unit
def test_saved_dirty_stale_reconcile_refuses_foreign_token(
    tmp_path, monkeypatch
):
    model, document, identities, service, _stale, wire, owner = (
        _install_saved_dirty_stale(tmp_path, monkeypatch)
    )
    rpc, _ = _install_rpc_runtime(
        monkeypatch,
        document=document,
        identities=identities,
        service=service,
        owner=owner,
        wire=wire,
    )
    foreign = dict(wire)
    foreign["token"] = "not-the-lease-token"

    result = rpc.lease_reconcile(foreign)

    assert result["success"] is False
    assert result["error_code"] == "LEASE_AUTHORIZATION_FAILED"
    assert service.get(wire["document_session_uuid"])["lease"]["state"] == (
        LeaseState.STALE.value
    )


@pytest.mark.unit
def test_saved_dirty_stale_reconcile_refuses_generation_mismatch(
    tmp_path, monkeypatch
):
    model, document, identities, service, stale, wire, owner = (
        _install_saved_dirty_stale(tmp_path, monkeypatch)
    )
    rpc, _ = _install_rpc_runtime(
        monkeypatch,
        document=document,
        identities=identities,
        service=service,
        owner=owner,
        wire=wire,
    )
    mismatched = dict(wire)
    mismatched["generation"] = int(wire["generation"]) + 1

    result = rpc.lease_reconcile(mismatched)

    assert result["success"] is False
    assert result["error_code"] == "LEASE_AUTHORIZATION_FAILED"
    assert "generation mismatch" in result["error"]
    assert service.get(wire["document_session_uuid"])["lease"]["state"] == (
        LeaseState.STALE.value
    )


@pytest.mark.unit
def test_saved_dirty_stale_reconcile_refuses_user_intervened(
    tmp_path, monkeypatch
):
    model, document, identities, service, stale, wire, owner = (
        _install_saved_dirty_stale(tmp_path, monkeypatch)
    )
    service._commit(stale, stale.revised(user_intervened=True))
    rpc, _ = _install_rpc_runtime(
        monkeypatch,
        document=document,
        identities=identities,
        service=service,
        owner=owner,
        wire=wire,
    )

    result = rpc.lease_reconcile(wire)

    assert result["success"] is False
    assert result["error_code"] == "LIVE_DOCUMENT_VALIDATION_FAILED"
    assert "user intervention" in result["error"]
    assert service.get(wire["document_session_uuid"])["lease"]["state"] == (
        LeaseState.STALE.value
    )


@pytest.mark.unit
def test_saved_dirty_stale_reconcile_refuses_content_changing_disk(
    tmp_path, monkeypatch
):
    model, document, identities, service, _stale, wire, owner = (
        _install_saved_dirty_stale(tmp_path, monkeypatch)
    )
    before = model.stat()
    original = model.read_bytes()

    def tamper_after_expectation_capture():
        changed = bytes(byte ^ 0xFF for byte in original)
        assert len(changed) == len(original)
        model.write_bytes(changed)
        os.utime(model, ns=(before.st_atime_ns, before.st_mtime_ns))

    events: list[str] = []
    dispatch = _TrackedGuiDispatch(events, after_first=tamper_after_expectation_capture)
    rpc, _ = _install_rpc_runtime(
        monkeypatch,
        document=document,
        identities=identities,
        service=service,
        owner=owner,
        wire=wire,
    )
    rpc._dispatch_gui = dispatch

    result = rpc.lease_reconcile(wire)

    assert result["success"] is False
    assert result["error_code"] == "LIVE_DOCUMENT_VALIDATION_FAILED"
    assert "does not exactly match" in result["error"]
    assert service.get(wire["document_session_uuid"])["lease"]["state"] == (
        LeaseState.STALE.value
    )


@pytest.mark.unit
def test_never_saved_stale_reconcile_refuses_stale_record_name_mismatch(
    recovery_snapshot_root, monkeypatch
):
    document, identities, service, stale, wire, owner, _snapshot_id = (
        _install_never_saved_dirty_stale(recovery_snapshot_root, monkeypatch)
    )
    service._commit(
        stale,
        stale.revised(document=replace(stale.document, name="StoredNeverSavedName")),
    )
    rpc, dispatch = _install_rpc_runtime(
        monkeypatch,
        document=document,
        identities=identities,
        service=service,
        owner=owner,
        wire=wire,
    )

    result = rpc.lease_reconcile(wire)

    assert result["success"] is False
    assert result["error_code"] == "LIVE_DOCUMENT_VALIDATION_FAILED"
    assert "does not match the stale lease" in result["error"]
    assert service.get(wire["document_session_uuid"])["lease"]["state"] == (
        LeaseState.STALE.value
    )
    assert dispatch.calls == 1


@pytest.mark.unit
def test_never_saved_stale_reconcile_refuses_proxy_session_mismatch(
    recovery_snapshot_root, monkeypatch
):
    document, identities, service, _stale, wire, owner, _snapshot_id = (
        _install_never_saved_dirty_stale(recovery_snapshot_root, monkeypatch)
    )
    rpc, _ = _install_rpc_runtime(
        monkeypatch,
        document=document,
        identities=identities,
        service=service,
        owner=owner,
        wire=wire,
    )
    foreign_session = str(uuid.uuid4())
    monkeypatch.setattr(
        identities,
        "registered_session_uuid",
        lambda _document: foreign_session,
    )

    result = rpc.lease_reconcile(wire)

    assert result["success"] is False
    assert result["error_code"] == "LIVE_DOCUMENT_VALIDATION_FAILED"
    assert "proxy is not registered" in result["error"]
    assert service.get(wire["document_session_uuid"])["lease"]["state"] == (
        LeaseState.STALE.value
    )


@pytest.mark.unit
def test_saved_dirty_stale_with_path_but_no_baseline_refuses_classify(
    tmp_path, monkeypatch
):
    model, document, identities, service, stale, wire, owner = (
        _install_saved_dirty_stale(tmp_path, monkeypatch)
    )
    assert stale.document.canonical_path
    assert stale.baseline is not None
    service._commit(stale, stale.revised(baseline=None))
    rpc, dispatch = _install_rpc_runtime(
        monkeypatch,
        document=document,
        identities=identities,
        service=service,
        owner=owner,
        wire=wire,
    )

    def unexpected_never_saved(*_args, **_kwargs):
        raise AssertionError(
            "path-without-baseline stale reconcile must not use never-saved path"
        )

    monkeypatch.setattr(
        addon_rpc, "_assert_never_saved_stale_continuity", unexpected_never_saved
    )

    result = rpc.lease_reconcile(wire)

    assert result["success"] is False
    assert result["error_code"] == "LIVE_DOCUMENT_VALIDATION_FAILED"
    assert "requires a saved verified baseline" in result["error"]
    assert service.get(wire["document_session_uuid"])["lease"]["state"] == (
        LeaseState.STALE.value
    )
    assert dispatch.calls == 1


@pytest.mark.unit
def test_never_saved_dirty_stale_reconcile_is_idempotent_after_success(
    recovery_snapshot_root, monkeypatch
):
    document, identities, service, _stale, wire, owner, snapshot_id = (
        _install_never_saved_dirty_stale(recovery_snapshot_root, monkeypatch)
    )
    rpc, dispatch = _install_rpc_runtime(
        monkeypatch,
        document=document,
        identities=identities,
        service=service,
        owner=owner,
        wire=wire,
    )

    first = rpc.lease_reconcile(wire)
    second = rpc.lease_reconcile(wire)

    assert first["success"] is True
    assert second["success"] is True
    assert second["lease"]["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert second["lease"]["document_state"]["dirty"] is True
    assert second["lease"]["document_state"]["snapshot_id"] == snapshot_id
    assert dispatch.calls == 3
