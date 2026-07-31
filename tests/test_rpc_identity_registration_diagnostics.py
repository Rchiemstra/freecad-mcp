"""P6 identity-registration failure diagnostics."""

from __future__ import annotations

import uuid

import pytest

from addon.FreeCADMCP.document_lease.identity import (
    DocumentIdentityService,
    IdentityMismatchError,
    capture_file_baseline,
)
from addon.FreeCADMCP.document_lease.model import LeaseOwner
from addon.FreeCADMCP.document_lease.observer import (
    IDENTITY_REGISTRATION_BRANCH_POST_INSPECTION_FAILED,
    IDENTITY_REGISTRATION_BRANCH_REGISTRATION_FAILED,
    register_live_document_recovery,
)
from addon.FreeCADMCP.document_lease.service import DocumentLeaseService
from addon.FreeCADMCP.rpc_server import rpc_server as addon_rpc


class FakeDocument:
    def __init__(self, name: str, filename: str, modified: bool = False):
        self.Name = name
        self.FileName = filename
        self.Modified = modified


def _owner() -> LeaseOwner:
    return LeaseOwner(
        addon_profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=10,
        freecad_process_started_at="2026-07-22T00:00:00Z",
        boot_id="boot-a",
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=20,
        mcp_process_started_at="2026-07-22T00:00:01Z",
        hostname="localhost",
        client="pytest",
        agent_id="agent-a",
    )


@pytest.mark.unit
def test_registration_failure_reports_drift_and_refresh_refusal(tmp_path, monkeypatch):
    model = tmp_path / "Diagnostics.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    content = b"original accepted baseline"
    model.write_bytes(content)
    document = FakeDocument("Diagnostics", str(model), modified=True)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    service.acquire(identity.session_uuid, _owner(), snapshot_id=str(uuid.uuid4()))

    replacement.write_bytes(b"user changed the archive")
    model.unlink()
    replacement.replace(model)

    monkeypatch.setattr(addon_rpc, "document_identity_service", identities)
    monkeypatch.setattr(addon_rpc, "document_lease_service", service)

    with pytest.raises(addon_rpc._import_document_lease().DocumentIdentityError) as exc:
        addon_rpc._ensure_v2_document(document)

    message = str(exc.value)
    assert "Diagnostics" in message
    assert IDENTITY_REGISTRATION_BRANCH_REGISTRATION_FAILED in message
    assert "file_identity" in message
    assert "automatic identity refresh was attempted and refused" in message
    assert exc.value.details["identity_refresh_attempted"] is True
    assert exc.value.details["identity_refresh_refused_reason"] == (
        "IDENTITY_REFRESH_CONTENT_HASH_CHANGED"
    )
    assert "restart" not in message.lower()
    assert "sidecar" not in message.lower()


@pytest.mark.unit
def test_register_live_document_recovery_returns_failure_details(tmp_path):
    model = tmp_path / "ObserverFailure.FCStd"
    model.write_bytes(b"changed content")
    document = FakeDocument("ObserverFailure", str(model), modified=True)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    service.acquire(identity.session_uuid, _owner(), snapshot_id=str(uuid.uuid4()))

    baseline = capture_file_baseline(model)
    replacement = tmp_path / "replacement.FCStd"
    replacement.write_bytes(b"new content after stale gui save")
    model.unlink()
    replacement.replace(model)
    assert capture_file_baseline(model).sha256 != baseline.sha256

    with pytest.raises(IdentityMismatchError):
        identities.register_document(document)

    repaired, imported, failure = register_live_document_recovery(service, document)

    assert repaired is None
    assert imported is None
    assert failure is not None
    assert failure.document_name == "ObserverFailure"
    assert failure.failure_branch == IDENTITY_REGISTRATION_BRANCH_REGISTRATION_FAILED
    assert failure.identity_refresh_attempted is True
    assert failure.identity_refresh_refused_reason == (
        "IDENTITY_REFRESH_CONTENT_HASH_CHANGED"
    )


@pytest.mark.unit
def test_post_registration_inspection_failed_rpc_reports_refresh_not_attempted(
    tmp_path, monkeypatch
):
    model = tmp_path / "PostInspect.FCStd"
    model.write_bytes(b"baseline content")
    document = FakeDocument("PostInspect", str(model))
    identities = DocumentIdentityService()
    service = DocumentLeaseService(identities)

    def inspect_side_effect(session_uuid, exact_document):
        raise RuntimeError("not the registered live document proxy")

    monkeypatch.setattr(
        identities, "inspect_registered_document", inspect_side_effect
    )
    monkeypatch.setattr(addon_rpc, "document_identity_service", identities)
    monkeypatch.setattr(addon_rpc, "document_lease_service", service)

    with pytest.raises(addon_rpc._import_document_lease().DocumentIdentityError) as exc:
        addon_rpc._ensure_v2_document(document)

    message = str(exc.value)
    assert IDENTITY_REGISTRATION_BRANCH_POST_INSPECTION_FAILED in message
    assert "automatic identity refresh was not attempted" in message
    assert exc.value.details["identity_refresh_attempted"] is False
    assert "identity_refresh_refused_reason" not in exc.value.details


@pytest.mark.unit
def test_post_registration_inspection_failed_observer_details(tmp_path, monkeypatch):
    model = tmp_path / "ObserverPostInspect.FCStd"
    model.write_bytes(b"baseline content")
    document = FakeDocument("ObserverPostInspect", str(model))
    identities = DocumentIdentityService()
    service = DocumentLeaseService(identities)

    def inspect_side_effect(session_uuid, exact_document):
        raise RuntimeError("not the registered live document proxy")

    monkeypatch.setattr(
        identities, "inspect_registered_document", inspect_side_effect
    )

    repaired, imported, failure = register_live_document_recovery(service, document)

    assert repaired is None
    assert imported is None
    assert failure is not None
    assert failure.failure_branch == IDENTITY_REGISTRATION_BRANCH_POST_INSPECTION_FAILED
    assert failure.identity_refresh_attempted is False
    assert failure.to_details()["identity_refresh_attempted"] is False
    assert "identity_refresh_refused_reason" not in failure.to_details()


@pytest.mark.unit
def test_lease_service_error_includes_identity_details():
    lease = addon_rpc._import_document_lease()
    exc = lease.DocumentIdentityError(
        "live document identity for 'RpcEnvelope' could not be registered",
        details={
            "document_name": "RpcEnvelope",
            "failure_branch": "registration_failed",
            "drifted_fields": ["file_identity"],
        },
    )
    payload = addon_rpc._lease_service_error(exc, request_id="req-1")

    assert payload["error_code"] == "DOCUMENT_IDENTITY_ERROR"
    assert payload["details"]["document_name"] == "RpcEnvelope"
    assert payload["details"]["drifted_fields"] == ["file_identity"]
    assert "token" not in str(payload)
