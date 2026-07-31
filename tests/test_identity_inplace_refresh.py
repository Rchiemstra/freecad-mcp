from __future__ import annotations

import os
import uuid
from dataclasses import replace

import pytest

from addon.FreeCADMCP.document_lease.identity import (
    DocumentIdentityService,
    IdentityMismatchError,
    UnknownDocumentError,
    capture_file_baseline,
)
from addon.FreeCADMCP.document_lease.model import LeaseOwner, LeaseState
from addon.FreeCADMCP.document_lease.observer import register_live_document_recovery
from addon.FreeCADMCP.document_lease.service import (
    CoordinationError,
    DocumentLeaseService,
    LeaseStateError,
)


class FakeDocument:
    def __init__(self, name: str, filename: str, modified: bool = False):
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
        client="pytest",
        agent_id="agent-a",
    )


def _atomic_replace_same_content(
    model,
    replacement,
    *,
    content: bytes,
) -> None:
    """Atomic rewrite with identical bytes; mtime may change like FreeCAD."""

    prior_mtime_ns = int(os.stat(model).st_mtime_ns) if model.exists() else 0
    replacement.write_bytes(content)
    if model.exists():
        model.unlink()
    replacement.replace(model)
    stat = os.stat(model)
    if int(stat.st_mtime_ns) == prior_mtime_ns:
        os.utime(model, ns=(stat.st_atime_ns, prior_mtime_ns + 1))


@pytest.mark.unit
def test_atomic_inplace_save_under_live_lease_refreshes_identity(tmp_path):
    model = tmp_path / "LiveLease.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    content = b"saved baseline bytes"
    model.write_bytes(content)
    baseline = capture_file_baseline(model)
    document = FakeDocument("LiveLease", str(model), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    grant = service.acquire(
        identity.session_uuid,
        _owner(),
        snapshot_id=_uuid(),
    )
    assert grant.record.state == LeaseState.LOCKED_IDLE
    assert grant.record.baseline == baseline

    _atomic_replace_same_content(
        model,
        replacement,
        content=content,
    )
    assert int(os.stat(model).st_mtime_ns) != baseline.mtime_ns
    observed = identities.inspect_registered_document(identity.session_uuid, document)
    assert observed.file_identity != identity.file_identity

    refreshed = service.try_baseline_preserving_document_identity_refresh(
        identity.session_uuid,
        document=document,
        trigger="test_inplace",
    )

    assert refreshed is not None
    assert refreshed.state == LeaseState.LOCKED_IDLE
    assert refreshed.generation == grant.record.generation
    assert refreshed.document.file_identity == observed.file_identity
    events = service.list_identity_refresh_events()
    assert len(events) == 1
    assert events[0]["trigger"] == "test_inplace"
    assert events[0]["baseline_sha256"] == baseline.sha256
    assert "token" not in events[0]


@pytest.mark.unit
def test_inplace_refresh_refuses_changed_content_hash(tmp_path):
    model = tmp_path / "ChangedHash.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    content = b"original accepted baseline"
    model.write_bytes(content)
    baseline = capture_file_baseline(model)
    document = FakeDocument("ChangedHash", str(model), modified=True)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())

    replacement.write_bytes(b"user changed the archive")
    model.unlink()
    replacement.replace(model)

    assert service.try_baseline_preserving_document_identity_refresh(
        identity.session_uuid,
        document=document,
    ) is None
    with pytest.raises(CoordinationError, match="content hash changed"):
        service.repair_registered_document_identity(document=document)


@pytest.mark.unit
def test_inplace_refresh_refuses_save_as_path_change(tmp_path):
    source = tmp_path / "source.FCStd"
    target = tmp_path / "target.FCStd"
    source.write_bytes(b"source baseline")
    document = FakeDocument("SaveAs", str(source), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())

    document.FileName = str(target)
    target.write_bytes(b"target baseline")

    with pytest.raises(CoordinationError, match="name or canonical path"):
        service.repair_registered_document_identity(document=document)


@pytest.mark.unit
def test_inplace_refresh_refuses_replacement_proxy(tmp_path):
    model = tmp_path / "Proxy.FCStd"
    model.write_bytes(b"proxy baseline")
    original = FakeDocument("Proxy", str(model), modified=False)
    replacement_proxy = FakeDocument("Proxy", str(model), modified=False)
    identities = DocumentIdentityService()
    identities.register_document(original)
    service = DocumentLeaseService(identities)

    with pytest.raises(UnknownDocumentError, match="registered live document"):
        service.repair_registered_document_identity(document=replacement_proxy)


@pytest.mark.unit
def test_inplace_refresh_refuses_missing_baseline(tmp_path):
    model = tmp_path / "NoBaseline.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    content = b"no baseline yet"
    model.write_bytes(content)
    baseline = capture_file_baseline(model)
    document = FakeDocument("NoBaseline", str(model), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    reservation = service.begin_acquisition(identity.session_uuid, _owner())
    assert reservation.record.baseline is None

    _atomic_replace_same_content(
        model,
        replacement,
        content=content,
    )
    assert int(os.stat(model).st_mtime_ns) != baseline.mtime_ns

    with pytest.raises(CoordinationError, match="baseline is missing"):
        service.repair_registered_document_identity(document=document)


@pytest.mark.unit
def test_register_live_document_recovery_repairs_leased_identity_drift(tmp_path):
    model = tmp_path / "RegistrationRepair.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    content = b"registration repair baseline"
    model.write_bytes(content)
    baseline = capture_file_baseline(model)
    document = FakeDocument("RegistrationRepair", str(model), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())

    _atomic_replace_same_content(
        model,
        replacement,
        content=content,
    )
    assert int(os.stat(model).st_mtime_ns) != baseline.mtime_ns
    identities._entries[identity.session_uuid].identity = replace(  # noqa: SLF001
        identity,
        file_identity=None,
    )

    with pytest.raises(IdentityMismatchError):
        identities.register_document(document)

    repaired, imported, _failure = register_live_document_recovery(service, document)

    assert imported is None
    assert repaired.file_identity == identities.inspect_registered_document(
        identity.session_uuid,
        document,
    ).file_identity
    assert service.get(identity.session_uuid)["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert len(service.list_identity_refresh_events()) == 1


@pytest.mark.unit
def test_finish_save_keeps_promoted_lease_on_baseline_preserving_atomic_save(tmp_path):
    from addon.FreeCADMCP.document_lease import observer as observer_mod

    model = tmp_path / "ObserverLease.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    content = b"observer baseline preserving save"
    model.write_bytes(content)
    baseline = capture_file_baseline(model)
    document = FakeDocument("ObserverLease", str(model), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    grant = service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)

    _atomic_replace_same_content(
        model,
        replacement,
        content=content,
    )
    assert int(os.stat(model).st_mtime_ns) != baseline.mtime_ns
    document.Modified = False

    record = observer.slotFinishSaveDocument(document, document.FileName)

    assert record.state == LeaseState.LOCKED_IDLE
    assert record.generation == grant.record.generation
    assert identities.register_document(document).file_identity != identity.file_identity
    assert len(service.list_identity_refresh_events()) == 1


@pytest.mark.unit
def test_inplace_refresh_updates_baseline_file_identity(tmp_path):
    model = tmp_path / "BaselineCoherence.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    content = b"baseline coherence bytes"
    model.write_bytes(content)
    baseline = capture_file_baseline(model)
    document = FakeDocument("BaselineCoherence", str(model), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    grant = service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())

    _atomic_replace_same_content(model, replacement, content=content)
    observed = identities.inspect_registered_document(identity.session_uuid, document)

    refreshed = service.try_baseline_preserving_document_identity_refresh(
        identity.session_uuid,
        document=document,
        trigger="test_baseline_coherence",
    )

    assert refreshed is not None
    assert refreshed.baseline is not None
    assert refreshed.baseline.file_identity == observed.file_identity
    assert refreshed.baseline.file_identity == refreshed.document.file_identity
    assert refreshed.baseline.size == baseline.size
    assert refreshed.baseline.sha256 == baseline.sha256
    assert refreshed.baseline.mtime_ns != baseline.mtime_ns
    fresh_baseline = capture_file_baseline(model)
    assert refreshed.baseline == fresh_baseline
    assert grant.record.baseline is not None
    assert grant.record.baseline.file_identity != refreshed.baseline.file_identity


@pytest.mark.unit
def test_finish_save_takeover_on_content_changing_save_under_locked_idle(tmp_path):
    from addon.FreeCADMCP.document_lease import observer as observer_mod

    model = tmp_path / "ContentChange.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    model.write_bytes(b"accepted baseline")
    document = FakeDocument("ContentChange", str(model), modified=True)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    grant = service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)

    replacement.write_bytes(b"user changed the archive")
    model.unlink()
    replacement.replace(model)
    document.Modified = False

    record = observer.slotFinishSaveDocument(document, document.FileName)

    assert record.state == LeaseState.USER_INTERVENED
    assert record.generation > grant.record.generation
    assert record.baseline is not None
    assert record.baseline.sha256 == grant.record.baseline.sha256


@pytest.mark.unit
def test_save_start_takeover_without_accepted_baseline(tmp_path):
    from addon.FreeCADMCP.document_lease import observer as observer_mod

    model = tmp_path / "SaveStartFence.FCStd"
    model.write_bytes(b"acquiring without baseline")
    document = FakeDocument("SaveStartFence", str(model), modified=True)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    service.begin_acquisition(identity.session_uuid, _owner())
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)

    record = observer.slotStartSaveDocument(document, document.FileName)

    assert record.state == LeaseState.USER_INTERVENED


@pytest.mark.unit
def test_save_start_defers_clean_baseline_preserving_save(tmp_path):
    from addon.FreeCADMCP.document_lease import observer as observer_mod

    model = tmp_path / "DeferredSave.FCStd"
    replacement = tmp_path / "replacement.FCStd"
    content = b"deferred save baseline"
    model.write_bytes(content)
    baseline = capture_file_baseline(model)
    document = FakeDocument("DeferredSave", str(model), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    grant = service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)

    started = observer.slotStartSaveDocument(document, document.FileName)
    assert _record_state(started) == LeaseState.LOCKED_IDLE.value

    _atomic_replace_same_content(model, replacement, content=content)
    assert int(os.stat(model).st_mtime_ns) != baseline.mtime_ns
    document.Modified = False

    record = observer.slotDeletedDocument(document)

    assert record.state == LeaseState.LOCKED_IDLE
    assert record.generation == grant.record.generation
    assert record.baseline.file_identity == identities.inspect_registered_document(
        identity.session_uuid,
        document,
    ).file_identity


@pytest.mark.unit
def test_recovery_identity_refresh_refuses_leased_state(tmp_path):
    model = tmp_path / "RecoveryGate.FCStd"
    model.write_bytes(b"leased recovery gate")
    document = FakeDocument("RecoveryGate", str(model), modified=False)
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    service = DocumentLeaseService(identities)
    service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())

    with pytest.raises(LeaseStateError, match="only after takeover"):
        service.refresh_local_recovery_document_identity(
            identity.session_uuid,
            document=document,
        )


def _record_state(record) -> str:
    if isinstance(record, dict):
        lease = record.get("lease")
        if isinstance(lease, dict):
            return str(lease.get("state", "") or "")
        return str(record.get("state", "") or "")
    value = getattr(record, "state", "")
    return str(getattr(value, "value", value) or "")
