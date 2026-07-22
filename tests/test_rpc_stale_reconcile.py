"""Focused RPC tests for phased, fail-closed stale reconciliation."""

from __future__ import annotations

import os
import threading
import uuid

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
    sidecar_path_for,
)
from addon.FreeCADMCP.rpc_server import rpc_server as addon_rpc


class _Document:
    def __init__(self, name: str, path: str) -> None:
        self.Name = name
        self.Label = name
        self.FileName = path
        self.Modified = False


class _TrackedGuiDispatch:
    def __init__(self, events: list[str], *, after_first=None) -> None:
        self.events = events
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
        client="stale-reconcile-test",
        agent_id="agent-a",
    )


def _install_stale_runtime(tmp_path, monkeypatch):
    model = tmp_path / "stale.FCStd"
    model.write_bytes(b"stable-baseline-payload")
    document = _Document("StaleDocument", str(model))
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
    stale = service.mark_stale(identity.session_uuid)
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
    wire = {
        "lease_id": grant.credential.lease_id,
        "document_session_uuid": grant.credential.document_session_uuid,
        "generation": grant.credential.generation,
        "token": grant.credential.token,
    }
    return model, document, identities, service, stale, wire


@pytest.fixture(autouse=True)
def _clean_request_identity():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


@pytest.mark.unit
def test_reconcile_hashes_off_gui_between_two_exact_gui_checks(tmp_path, monkeypatch):
    model, _document, identities, service, _stale, wire = _install_stale_runtime(
        tmp_path, monkeypatch
    )
    events: list[str] = []
    dispatch = _TrackedGuiDispatch(events)
    rpc = addon_rpc.FreeCADRPC()
    rpc._dispatch_gui = dispatch

    original_capture = lease_core.capture_file_baseline

    def capture_off_gui(path, *, platform=None):
        assert dispatch.in_gui is False
        assert threading.get_ident() not in dispatch.gui_thread_ids
        events.append("full-sha-capture")
        return original_capture(path, platform=platform)

    original_inspect = identities.inspect_registered_document

    def inspect_on_gui(session_uuid, document):
        assert dispatch.in_gui is True
        events.append("identity-inspect")
        return original_inspect(session_uuid, document)

    monkeypatch.setattr(lease_core, "capture_file_baseline", capture_off_gui)
    monkeypatch.setattr(identities, "inspect_registered_document", inspect_on_gui)

    result = rpc.lease_reconcile(wire)

    assert result["success"] is True
    assert result["lease"]["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert service.get(wire["document_session_uuid"])["lease"]["state"] == (
        LeaseState.LOCKED_IDLE.value
    )
    assert dispatch.calls == 2
    assert events.index("gui-exit-1") < events.index("full-sha-capture")
    assert events.index("full-sha-capture") < events.index("gui-enter-2")
    assert model.exists()


@pytest.mark.unit
def test_same_size_same_mtime_content_tamper_remains_stale(tmp_path, monkeypatch):
    model, _document, _identities, service, _stale, wire = _install_stale_runtime(
        tmp_path, monkeypatch
    )
    before = model.stat()
    original = model.read_bytes()

    def tamper_after_expectation_capture():
        changed = bytes(byte ^ 0xFF for byte in original)
        assert len(changed) == len(original)
        model.write_bytes(changed)
        os.utime(model, ns=(before.st_atime_ns, before.st_mtime_ns))

    events: list[str] = []
    dispatch = _TrackedGuiDispatch(
        events, after_first=tamper_after_expectation_capture
    )
    rpc = addon_rpc.FreeCADRPC()
    rpc._dispatch_gui = dispatch

    result = rpc.lease_reconcile(wire)

    assert result["success"] is False
    assert result["error_code"] == "LIVE_DOCUMENT_VALIDATION_FAILED"
    assert "does not exactly match" in result["error"]
    status = service.get(wire["document_session_uuid"])
    assert status["lease"]["state"] == LeaseState.STALE.value
    # A mismatched baseline never reaches the transition owner.
    assert status["document_state"]["error"]["code"] == "LEASE_STALE"


@pytest.mark.unit
def test_unstable_hash_capture_never_runs_final_gui_transition(tmp_path, monkeypatch):
    _model, _document, _identities, service, _stale, wire = _install_stale_runtime(
        tmp_path, monkeypatch
    )
    dispatch = _TrackedGuiDispatch([])
    rpc = addon_rpc.FreeCADRPC()
    rpc._dispatch_gui = dispatch

    def unstable_capture(*_args, **_kwargs):
        assert dispatch.in_gui is False
        raise lease_core.DocumentIdentityError(
            "document changed while its baseline was captured"
        )

    monkeypatch.setattr(lease_core, "capture_file_baseline", unstable_capture)

    result = rpc.lease_reconcile(wire)

    assert result["success"] is False
    assert result["error_code"] == "LIVE_DOCUMENT_VALIDATION_FAILED"
    assert dispatch.calls == 1
    assert service.get(wire["document_session_uuid"])["lease"]["state"] == (
        LeaseState.STALE.value
    )


@pytest.mark.unit
def test_sidecar_authority_change_during_hash_remains_stale(tmp_path, monkeypatch):
    model, _document, _identities, service, stale, wire = _install_stale_runtime(
        tmp_path, monkeypatch
    )

    def replace_sidecar_after_expectation_capture():
        path = sidecar_path_for(model)
        changed = stale.revised(current_operation="concurrent recovery")
        service.sidecar_store.replace(path, changed, expected=stale)

    rpc = addon_rpc.FreeCADRPC()
    rpc._dispatch_gui = _TrackedGuiDispatch(
        [], after_first=replace_sidecar_after_expectation_capture
    )

    result = rpc.lease_reconcile(wire)

    assert result["success"] is False
    assert result["error_code"] == "LEASE_COORDINATION_LOST"
    # The registry never transitions to writable state when disk authority
    # changes during the off-GUI hash window.
    assert service.get(wire["document_session_uuid"])["lease"]["state"] == (
        LeaseState.STALE.value
    )
