"""P7 cross-layer identity refresh boundary tests (S6-A).

Wires service identity refresh through ``register_live_document_recovery`` and
RPC ``_ensure_v2_document`` so selector resolution exercises the full path,
not isolated unit predicates alone.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import replace

import pytest

from addon.FreeCADMCP.document_lease.identity import (
    DocumentIdentityService,
    IdentityMismatchError,
    capture_file_baseline,
)
from addon.FreeCADMCP.document_lease.model import LeaseOwner, LeaseState
from addon.FreeCADMCP.document_lease.observer import (
    IDENTITY_REGISTRATION_BRANCH_REGISTRATION_FAILED,
    register_live_document_recovery,
)
from addon.FreeCADMCP.document_lease.service import DocumentLeaseService
from addon.FreeCADMCP.rpc_server import rpc_server as addon_rpc


class FakeDocument:
    def __init__(self, name: str, filename: str, *, modified: bool = False):
        self.Name = name
        self.FileName = filename
        self.Modified = modified


def _uuid() -> str:
    return str(uuid.uuid4())


def _owner() -> LeaseOwner:
    return LeaseOwner(
        addon_profile_id=_uuid(),
        addon_runtime_id=_uuid(),
        freecad_pid=10,
        freecad_process_started_at="2026-07-22T00:00:00Z",
        boot_id="boot-a",
        mcp_instance_id=_uuid(),
        mcp_pid=20,
        mcp_process_started_at="2026-07-22T00:00:01Z",
        hostname="localhost",
        client="pytest-p7-identity",
        agent_id="agent-a",
    )


def _atomic_replace_same_content(model, replacement, *, content: bytes) -> None:
    replacement.write_bytes(content)
    if model.exists():
        model.unlink()
    replacement.replace(model)


def _install_rpc_services(
    monkeypatch,
    *,
    identities: DocumentIdentityService,
    service: DocumentLeaseService,
) -> None:
    monkeypatch.setattr(addon_rpc, "document_identity_service", identities)
    monkeypatch.setattr(addon_rpc, "document_lease_service", service)


def _ensure_v2(document) -> object:
    return addon_rpc._ensure_v2_document(document)


@pytest.mark.unit
def test_rpc_accepts_baseline_preserving_atomic_rewrite_under_live_lease(
    tmp_path, monkeypatch
):
    model = tmp_path / "LiveLeaseRpc.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    content = b"rpc live lease baseline bytes"
    model.write_bytes(content)
    baseline = capture_file_baseline(model)
    document = FakeDocument("LiveLeaseRpc", str(model), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    grant = service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())
    _install_rpc_services(monkeypatch, identities=identities, service=service)

    _atomic_replace_same_content(model, replacement, content=content)
    assert int(os.stat(model).st_mtime_ns) != baseline.mtime_ns
    with pytest.raises(IdentityMismatchError):
        identities.register_document(document)

    resolved = _ensure_v2(document)

    assert resolved.session_uuid == identity.session_uuid
    assert resolved.file_identity == identities.inspect_registered_document(
        identity.session_uuid, document
    ).file_identity
    assert service.get(identity.session_uuid)["lease"]["state"] == (
        LeaseState.LOCKED_IDLE.value
    )
    assert service.get(identity.session_uuid)["generation"] == grant.record.generation
    events = service.list_identity_refresh_events()
    assert len(events) == 1
    assert "token" not in str(events)


@pytest.mark.unit
def test_rpc_accepts_identity_drift_under_stale_lease(tmp_path, monkeypatch):
    model = tmp_path / "StaleLeaseRpc.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    content = b"stale lease identity drift bytes"
    model.write_bytes(content)
    document = FakeDocument("StaleLeaseRpc", str(model), modified=True)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    grant = service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())
    service.begin_mutation(grant.credential, operation="probe")
    service.complete_operation(grant.credential, dirty=True)
    stale = service.mark_stale(identity.session_uuid)
    assert stale.state == LeaseState.STALE
    _install_rpc_services(monkeypatch, identities=identities, service=service)

    _atomic_replace_same_content(model, replacement, content=content)
    with pytest.raises(IdentityMismatchError):
        identities.register_document(document)

    resolved = _ensure_v2(document)

    assert resolved.session_uuid == identity.session_uuid
    assert service.get(identity.session_uuid)["lease"]["state"] == LeaseState.STALE.value
    assert len(service.list_identity_refresh_events()) == 1


@pytest.mark.unit
def test_rpc_refuses_save_as_path_change_under_live_lease(tmp_path, monkeypatch):
    source = tmp_path / "source.FCStd"
    target = tmp_path / "target.FCStd"
    source.write_bytes(b"source baseline")
    document = FakeDocument("SaveAsRpc", str(source), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())
    _install_rpc_services(monkeypatch, identities=identities, service=service)

    document.FileName = str(target)
    target.write_bytes(b"target baseline")

    lease = addon_rpc._import_document_lease()
    with pytest.raises(lease.DocumentIdentityError) as exc:
        _ensure_v2(document)

    message = str(exc.value)
    assert "SaveAsRpc" in message
    assert IDENTITY_REGISTRATION_BRANCH_REGISTRATION_FAILED in message
    assert exc.value.details["identity_refresh_attempted"] is True
    assert exc.value.details["identity_refresh_refused_reason"] == (
        "IDENTITY_REFRESH_NAME_OR_PATH_CHANGED"
    )


@pytest.mark.unit
def test_rpc_refuses_replacement_proxy_under_live_lease(tmp_path, monkeypatch):
    model = tmp_path / "ProxyRpc.FCStd"
    model.write_bytes(b"proxy baseline")
    original = FakeDocument("ProxyRpc", str(model), modified=False)
    replacement_proxy = FakeDocument("ProxyRpc", str(model), modified=False)
    identities = DocumentIdentityService()
    identities.register_document(original)
    service = DocumentLeaseService(identities)
    service.acquire(
        identities.registered_session_uuid(original),
        _owner(),
        snapshot_id=_uuid(),
    )
    _install_rpc_services(monkeypatch, identities=identities, service=service)

    lease = addon_rpc._import_document_lease()
    with pytest.raises(lease.DocumentIdentityError) as exc:
        _ensure_v2(replacement_proxy)

    assert exc.value.details["identity_refresh_attempted"] is True
    assert exc.value.details["identity_refresh_refused_reason"] == (
        "IDENTITY_REFRESH_REPLACEMENT_PROXY"
    )
    message = str(exc.value)
    assert "IDENTITY_REFRESH_REPLACEMENT_PROXY" in message


@pytest.mark.unit
def test_rpc_refuses_changed_content_hash_under_live_lease(tmp_path, monkeypatch):
    model = tmp_path / "ChangedHashRpc.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    content = b"accepted rpc baseline"
    model.write_bytes(content)
    document = FakeDocument("ChangedHashRpc", str(model), modified=True)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())
    _install_rpc_services(monkeypatch, identities=identities, service=service)

    replacement.write_bytes(b"user changed the archive")
    model.unlink()
    replacement.replace(model)

    lease = addon_rpc._import_document_lease()
    with pytest.raises(lease.DocumentIdentityError) as exc:
        _ensure_v2(document)

    assert exc.value.details["identity_refresh_attempted"] is True
    assert exc.value.details["identity_refresh_refused_reason"] == (
        "IDENTITY_REFRESH_CONTENT_HASH_CHANGED"
    )


@pytest.mark.unit
def test_rpc_refuses_missing_baseline_acquiring_record(tmp_path, monkeypatch):
    model = tmp_path / "NoBaselineRpc.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    content = b"acquiring without baseline"
    model.write_bytes(content)
    document = FakeDocument("NoBaselineRpc", str(model), modified=True)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    reservation = service.begin_acquisition(identity.session_uuid, _owner())
    assert reservation.record.baseline is None
    _install_rpc_services(monkeypatch, identities=identities, service=service)

    _atomic_replace_same_content(model, replacement, content=content)

    lease = addon_rpc._import_document_lease()
    with pytest.raises(lease.DocumentIdentityError) as exc:
        _ensure_v2(document)

    assert exc.value.details["identity_refresh_refused_reason"] == (
        "IDENTITY_REFRESH_BASELINE_MISSING"
    )
    repaired, imported, failure = register_live_document_recovery(service, document)
    assert repaired is None
    assert imported is None
    assert failure is not None
    assert failure.identity_refresh_refused_reason in {
        "IDENTITY_REFRESH_BASELINE_MISSING",
        "IDENTITY_REFRESH_NO_ACCEPTED_BASELINE",
    }


@pytest.mark.unit
def test_rpc_refuses_changed_document_name_under_live_lease(tmp_path, monkeypatch):
    model = tmp_path / "RenamedRpc.FCStd"
    model.write_bytes(b"rename baseline")
    document = FakeDocument("RenamedRpc", str(model), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    grant = service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())
    _install_rpc_services(monkeypatch, identities=identities, service=service)

    document.Name = "RenamedRpcChanged"
    lease = addon_rpc._import_document_lease()
    with pytest.raises(lease.DocumentIdentityError) as exc:
        _ensure_v2(document)

    assert exc.value.details["identity_refresh_attempted"] is True
    assert exc.value.details["identity_refresh_refused_reason"] == (
        "IDENTITY_REFRESH_NAME_OR_PATH_CHANGED"
    )
    assert service.get(identity.session_uuid)["generation"] == grant.record.generation
