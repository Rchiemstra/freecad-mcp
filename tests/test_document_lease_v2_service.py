"""Focused tests for mandatory credential fencing and server-owned state."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import replace

import pytest

from addon.FreeCADMCP.document_lease import service as lease_service_module
from addon.FreeCADMCP.document_lease.identity import (
    DocumentIdentityService,
    canonicalize_path,
    capture_file_baseline,
    file_identity_for_path,
)
from addon.FreeCADMCP.document_lease.model import (
    DocumentSelector,
    LeaseCredential,
    LiveDocumentValidation,
    LeaseOwner,
    LeaseState,
    SaveAsMigrationRole,
)
from addon.FreeCADMCP.document_lease.service import (
    AuthorizationError,
    CleanReleaseError,
    CoordinationError,
    DirtyAcquisitionError,
    DocumentLeaseService,
    ForeignRecoveryError,
    LeaseConflictError,
    LeaseServiceError,
    LeaseStateError,
    LocalRuntimeIdentity,
    LocalRecoveryError,
    LiveDocumentValidationError,
    ProcessLivenessEvidence,
)
from addon.FreeCADMCP.document_lease.sidecar import SidecarConflictError, SidecarStore


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


def _validation(
    identities: DocumentIdentityService,
    credential: LeaseCredential,
    *,
    modified: bool = False,
    baseline_validated: bool = True,
) -> LiveDocumentValidation:
    identity = identities.resolve(credential.document_session_uuid)
    baseline = (
        capture_file_baseline(identity.canonical_path, platform=identities.platform)
        if identity.canonical_path
        else None
    )
    return LiveDocumentValidation(
        document=identity,
        document_modified=modified,
        baseline=baseline,
        baseline_validated=baseline_validated,
    )


def _local_runtime(
    owner: LeaseOwner,
    *,
    boot_id: str | None = None,
    freecad_pid: int = 99,
    freecad_process_started_at: str = "2026-07-22T00:02:00Z",
    hostname: str | None = None,
    addon_runtime_id: str | None = None,
) -> LocalRuntimeIdentity:
    return LocalRuntimeIdentity(
        addon_profile_id=_uuid(),
        addon_runtime_id=addon_runtime_id or _uuid(),
        freecad_pid=freecad_pid,
        freecad_process_started_at=freecad_process_started_at,
        boot_id=boot_id or owner.boot_id,
        hostname=hostname or owner.hostname,
    )


def _foreign_recovery_setup(
    tmp_path,
    *,
    runtime_factory=_local_runtime,
    process_liveness_probe=None,
):
    model = tmp_path / "foreign-recovery.FCStd"
    model.write_bytes(b"valid archive")
    owner = _owner()

    foreign_identities = DocumentIdentityService()
    foreign_document = foreign_identities.register(name="Foreign", path=model)
    foreign_service = DocumentLeaseService(foreign_identities)
    grant = foreign_service.acquire(
        foreign_document.session_uuid,
        owner,
        snapshot_id=_uuid(),
    )

    local_identities = DocumentIdentityService()
    local_document = local_identities.register(name="Recovered", path=model)
    recovery_service = DocumentLeaseService(
        local_identities,
        local_runtime_identity=runtime_factory(owner),
        process_liveness_probe=process_liveness_probe,
    )
    return (
        model,
        owner,
        grant,
        foreign_service,
        local_document,
        recovery_service,
    )


class _Clock:
    def __init__(self):
        self.ns = 1_000_000_000
        self.wall = 0

    def monotonic_ns(self):
        return self.ns

    def utc(self):
        self.wall += 1
        return f"2026-07-22T00:00:{self.wall:02d}Z"

    def advance(self, seconds):
        self.ns += int(seconds * 1e9)


@pytest.fixture
def saved_lease(tmp_path):
    model = tmp_path / "model.FCStd"
    model.write_bytes(b"valid archive")
    identities = DocumentIdentityService()
    identity = identities.register(name="Model", path=model)
    clock = _Clock()
    service = DocumentLeaseService(
        identities,
        SidecarStore(),
        utc_clock=clock.utc,
        monotonic_ns=clock.monotonic_ns,
    )
    grant = service.acquire(
        identity.session_uuid,
        _owner(),
        task_summary="Build pad",
        snapshot_id=_uuid(),
    )
    return model, identities, service, clock, grant


@pytest.mark.unit
def test_unresolved_owner_predicate_includes_error_recovery_state(saved_lease):
    _model, identities, service, _clock, grant = saved_lease
    runtime_id = grant.record.owner.mcp_instance_id
    assert service.has_unresolved_owner(runtime_id) is True
    assert service.has_unresolved_owner(_uuid()) is False

    service.begin_mutation(grant.credential, operation="Failing edit")
    service.record_error(
        grant.credential,
        code="TEST_FAILURE",
        message="retained for recovery",
        dirty=False,
    )
    assert service.has_unresolved_owner(runtime_id) is True


@pytest.mark.unit
def test_metadata_never_echoes_presented_credential(saved_lease):
    model, _identities, service, _clock, grant = saved_lease
    sentinel = grant.credential.token
    fingerprint = grant.record.token_fingerprint

    public = service.update_metadata(
        grant.credential,
        task_summary=f"task {sentinel} {fingerprint}",
        current_operation=f"operation {sentinel} {fingerprint}",
    )
    heartbeat = service.heartbeat(
        grant.credential,
        current_operation=f"heartbeat {sentinel} {fingerprint}",
        task_summary=f"heartbeat task {sentinel} {fingerprint}",
    )
    sidecar = model.with_name(model.name + ".freecad-mcp.lock")
    persisted = json.loads(sidecar.read_text(encoding="utf-8"))

    rendered_values = (
        repr(public),
        repr(heartbeat),
        persisted["lease"]["current_operation"],
        persisted["lease"]["task_summary"],
    )
    for rendered in rendered_values:
        assert sentinel not in rendered
        assert fingerprint not in rendered
    for rendered in rendered_values[:3]:
        assert "<redacted>" in rendered


@pytest.mark.unit
class TestDocumentLeaseAuthorization:
    def test_saved_acquisition_publishes_acquiring_before_hash(
        self, tmp_path, monkeypatch
    ):
        model = tmp_path / "reserved-first.FCStd"
        model.write_bytes(b"archive")
        identities = DocumentIdentityService()
        identity = identities.register(name="ReservedFirst", path=model)
        service = DocumentLeaseService(identities)
        sidecar = model.with_name(model.name + ".freecad-mcp.lock")
        observed_states = []

        def capture_after_reservation(path, *, platform=None):
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            observed_states.append(payload["lease"]["state"])
            return capture_file_baseline(path, platform=platform)

        monkeypatch.setattr(
            lease_service_module,
            "capture_file_baseline",
            capture_after_reservation,
        )

        grant = service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())

        assert observed_states == [LeaseState.ACQUIRING.value]
        assert grant.record.state == LeaseState.LOCKED_IDLE
        assert grant.record.baseline is not None
        assert grant.record.validation_complete is True

    @pytest.mark.parametrize("kind", ["missing", "directory"])
    def test_saved_acquisition_rejects_nonregular_path_and_rolls_back(
        self, tmp_path, kind
    ):
        path = tmp_path / "unavailable.FCStd"
        if kind == "directory":
            path.mkdir()
        identities = DocumentIdentityService()
        identity = identities.register(name="Unavailable", path=path)
        service = DocumentLeaseService(identities)
        sidecar = path.with_name(path.name + ".freecad-mcp.lock")

        with pytest.raises(LeaseServiceError, match="regular file"):
            service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())

        assert service.get(identity.session_uuid) is None
        assert not sidecar.exists()

    def test_saved_acquisition_never_promotes_validation_without_baseline(
        self, tmp_path
    ):
        model = tmp_path / "missing-baseline.FCStd"
        model.write_bytes(b"archive")
        identities = DocumentIdentityService()
        identity = identities.register(name="MissingBaseline", path=model)
        service = DocumentLeaseService(identities)
        reservation = service.begin_acquisition(identity.session_uuid, _owner())

        assert reservation.record.state == LeaseState.ACQUIRING
        with pytest.raises(LeaseServiceError, match="requires a file baseline"):
            service.complete_acquisition(
                reservation.credential,
                baseline=None,
                baseline_validated=True,
                snapshot_id=_uuid(),
            )
        assert service.get(identity.session_uuid)["lease"]["state"] == "ACQUIRING"
        service.abort_acquisition(reservation.credential)

    def test_failed_acquisition_rollback_retains_visible_error_record(
        self, tmp_path, monkeypatch
    ):
        missing = tmp_path / "rollback-failure.FCStd"
        identities = DocumentIdentityService()
        identity = identities.register(name="RollbackFailure", path=missing)
        service = DocumentLeaseService(identities)
        sidecar = missing.with_name(missing.name + ".freecad-mcp.lock")

        def fail_delete(_path, *, expected):
            del expected
            raise SidecarConflictError("simulated rollback CAS failure")

        monkeypatch.setattr(service.sidecar_store, "delete", fail_delete)

        with pytest.raises(CoordinationError, match="could not be rolled back"):
            service.acquire(identity.session_uuid, _owner(), snapshot_id=_uuid())

        status = service.get(identity.session_uuid)
        assert status["lease"]["state"] == LeaseState.LOCKED_ERROR.value
        assert status["document_state"]["error"]["code"] == (
            "ACQUISITION_ROLLBACK_FAILED"
        )
        assert sidecar.exists()

    def test_acquisition_returns_raw_token_once_and_status_is_redacted(
        self, saved_lease
    ):
        model, identities, service, clock, grant = saved_lease
        token = grant.credential.token
        acquisition = grant.to_dict()
        assert acquisition["credential"]["token"] == token
        public = service.get(grant.credential.document_session_uuid)
        assert "token_fingerprint" not in public
        assert token not in json.dumps(public)
        assert token not in model.with_name(model.name + ".freecad-mcp.lock").read_text(
            encoding="utf-8"
        )
        sidecar_payload = json.loads(
            model.with_name(model.name + ".freecad-mcp.lock").read_text(
                encoding="utf-8"
            )
        )
        assert sidecar_payload["lease"]["task_summary"] == ""
        assert public["lease"]["task_summary"] == "Build pad"

    def test_all_credential_fields_are_mandatory(self, saved_lease):
        _, _, service, _, grant = saved_lease
        valid = grant.credential
        for invalid in (
            replace(valid, lease_id=""),
            replace(valid, document_session_uuid=""),
            replace(valid, generation=0),
            replace(valid, token=""),
            replace(valid, token="wrong"),
            replace(valid, generation=valid.generation + 1),
        ):
            with pytest.raises(AuthorizationError):
                service.authorize(invalid)

    def test_selector_is_an_additional_identity_assertion(self, tmp_path, saved_lease):
        _, identities, service, _, grant = saved_lease
        other_file = tmp_path / "other.FCStd"
        other_file.write_bytes(b"other")
        identities.register(name="Other", path=other_file)
        with pytest.raises(AuthorizationError):
            service.authorize(
                grant.credential,
                selector=DocumentSelector(document_name="Other"),
            )

    def test_sidecar_replacement_fails_closed(self, saved_lease):
        model, _, service, _, grant = saved_lease
        sidecar = model.with_name(model.name + ".freecad-mcp.lock")
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        payload["record_revision"] += 1
        sidecar.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(CoordinationError):
            service.authorize(grant.credential)

        effective = service.get_effective(grant.credential.document_session_uuid)
        assert effective["lease"]["state"] == LeaseState.LOCKED_ERROR.value
        assert effective["coordination_lost"] is True
        assert effective["document_state"]["error"]["code"] == (
            "SIDECAR_AUTHORITY_MISMATCH"
        )
        assert grant.credential.token not in json.dumps(effective)

    def test_missing_local_sidecar_is_visibly_fail_closed(self, saved_lease):
        model, _, service, _, grant = saved_lease
        sidecar = model.with_name(model.name + ".freecad-mcp.lock")
        sidecar.unlink()

        effective = service.get_effective(grant.credential.document_session_uuid)
        listed = service.list_effective_records()

        assert effective["source"] == "local_coordination_error"
        assert effective["lease"]["state"] == LeaseState.LOCKED_ERROR.value
        assert effective["document_state"]["error"]["code"] == "SIDECAR_MISSING"
        assert listed == [effective]
        with pytest.raises(CoordinationError):
            service.authorize(grant.credential)

    def test_preexisting_dirty_document_requires_local_adoption(self, tmp_path):
        model = tmp_path / "dirty.FCStd"
        model.write_bytes(b"dirty")
        identities = DocumentIdentityService()
        identity = identities.register(name="Dirty", path=model)
        service = DocumentLeaseService(identities)
        with pytest.raises(DirtyAcquisitionError):
            service.acquire(identity.session_uuid, _owner(), document_dirty=True)
        assert not model.with_name(model.name + ".freecad-mcp.lock").exists()

    def test_malformed_foreign_sidecar_is_preserved(self, tmp_path):
        model = tmp_path / "foreign.FCStd"
        model.write_bytes(b"file")
        sidecar = model.with_name(model.name + ".freecad-mcp.lock")
        sidecar.write_text("malformed foreign record", encoding="utf-8")
        identities = DocumentIdentityService()
        identity = identities.register(name="Foreign", path=model)
        service = DocumentLeaseService(identities)
        with pytest.raises(LeaseConflictError):
            service.acquire(identity.session_uuid, _owner())
        assert sidecar.read_text(encoding="utf-8") == "malformed foreign record"


@pytest.mark.unit
class TestForeignRecoveryImport:
    def test_import_is_redacted_immutable_and_blocks_new_acquisition(self, tmp_path):
        (
            _,
            _,
            grant,
            _,
            local_document,
            service,
        ) = _foreign_recovery_setup(tmp_path)

        imported = service.import_adjacent_foreign_recovery(
            local_document.session_uuid,
            live_document=local_document,
        )

        assert imported["source"] == "foreign_recovery"
        assert imported["immutable"] is True
        assert imported["foreign_document_session_uuid"] == (
            grant.record.document.session_uuid
        )
        assert imported["local_document"]["session_uuid"] == (
            local_document.session_uuid
        )
        assert "token_fingerprint" not in imported
        assert grant.credential.token not in json.dumps(imported)
        assert service.get(local_document.session_uuid) is None
        assert service.get_foreign_recovery(local_document.session_uuid) == imported
        assert service.get_effective(local_document.session_uuid) == imported
        assert service.list_foreign_recoveries() == [imported]
        assert service.list_effective_records() == [imported]

        with pytest.raises(LeaseConflictError, match="foreign recovery"):
            service.acquire(
                local_document.session_uuid,
                _owner(),
                snapshot_id=_uuid(),
            )

    @pytest.mark.parametrize(
        "payload",
        [b"not json", json.dumps({"schema_version": 999}).encode("utf-8")],
        ids=["malformed", "unknown-schema"],
    )
    def test_malformed_or_unknown_sidecar_is_never_imported_or_changed(
        self, tmp_path, payload
    ):
        model = tmp_path / "untrusted.FCStd"
        model.write_bytes(b"archive")
        sidecar = model.with_name(model.name + ".freecad-mcp.lock")
        sidecar.write_bytes(payload)
        identities = DocumentIdentityService()
        document = identities.register(name="Untrusted", path=model)
        service = DocumentLeaseService(
            identities,
            SidecarStore(strict_permissions=False),
        )

        with pytest.raises(ForeignRecoveryError, match="invalid"):
            service.import_adjacent_foreign_recovery(
                document.session_uuid,
                live_document=document,
            )

        assert sidecar.read_bytes() == payload
        assert service.get_foreign_recovery(document.session_uuid) is None
        with pytest.raises(LeaseConflictError):
            service.acquire(
                document.session_uuid,
                _owner(),
                snapshot_id=_uuid(),
            )

    def test_import_rejects_sidecar_for_nonmatching_document_identity(self, tmp_path):
        (
            model,
            _,
            grant,
            foreign_service,
            local_document,
            service,
        ) = _foreign_recovery_setup(tmp_path)
        sidecar = model.with_name(model.name + ".freecad-mcp.lock")
        mismatched = grant.record.revised(
            document=replace(
                grant.record.document,
                comparison_key=grant.record.document.comparison_key + ".different",
            )
        )
        foreign_service.sidecar_store.replace(
            sidecar,
            mismatched,
            expected=grant.record,
        )

        with pytest.raises(ForeignRecoveryError, match="different document path"):
            service.import_adjacent_foreign_recovery(
                local_document.session_uuid,
                live_document=local_document,
            )

        assert service.get_foreign_recovery(local_document.session_uuid) is None
        assert foreign_service.sidecar_store.read(sidecar) == mismatched

    def test_takeover_requires_explicit_confirmation_and_dead_owner_proof(
        self, tmp_path
    ):
        (
            model,
            owner,
            _,
            _,
            local_document,
            service,
        ) = _foreign_recovery_setup(
            tmp_path,
        )
        service._process_liveness_probe = lambda _pid: ProcessLivenessEvidence(
            exists=True,
            process_started_at=owner.freecad_process_started_at,
        )
        service.import_adjacent_foreign_recovery(
            local_document.session_uuid,
            live_document=local_document,
        )
        sidecar = model.with_name(model.name + ".freecad-mcp.lock")
        before = sidecar.read_bytes()

        with pytest.raises(ForeignRecoveryError, match="explicit local confirmation"):
            service.confirmed_takeover_foreign_recovery(
                local_document.session_uuid,
                live_document=local_document,
                confirmed=False,
                document_dirty=False,
                reason="User selected Take Over",
            )
        with pytest.raises(ForeignRecoveryError, match="still alive"):
            service.confirmed_takeover_foreign_recovery(
                local_document.session_uuid,
                live_document=local_document,
                confirmed=True,
                document_dirty=False,
                reason="User selected Take Over",
            )

        assert sidecar.read_bytes() == before
        assert service.get(local_document.session_uuid) is None
        assert service.get_foreign_recovery(local_document.session_uuid) is not None

    @pytest.mark.parametrize("evidence", [None, ProcessLivenessEvidence(None)])
    def test_takeover_fails_closed_when_same_boot_liveness_is_unknown(
        self, tmp_path, evidence
    ):
        probe = None if evidence is None else lambda _pid: evidence
        (
            _,
            _,
            _,
            _,
            local_document,
            service,
        ) = _foreign_recovery_setup(
            tmp_path,
            process_liveness_probe=probe,
        )
        service.import_adjacent_foreign_recovery(
            local_document.session_uuid,
            live_document=local_document,
        )

        with pytest.raises(ForeignRecoveryError, match="unavailable|unknown"):
            service.confirmed_takeover_foreign_recovery(
                local_document.session_uuid,
                live_document=local_document,
                confirmed=True,
                document_dirty=False,
                reason="Confirmed local recovery",
            )

    def test_takeover_refuses_owner_on_another_host(self, tmp_path):
        def other_host_runtime(owner):
            return _local_runtime(owner, hostname="other-host")

        (
            _,
            _,
            _,
            _,
            local_document,
            service,
        ) = _foreign_recovery_setup(
            tmp_path,
            runtime_factory=other_host_runtime,
            process_liveness_probe=lambda _pid: ProcessLivenessEvidence(False),
        )
        service.import_adjacent_foreign_recovery(
            local_document.session_uuid,
            live_document=local_document,
        )

        with pytest.raises(ForeignRecoveryError, match="another host"):
            service.confirmed_takeover_foreign_recovery(
                local_document.session_uuid,
                live_document=local_document,
                confirmed=True,
                document_dirty=False,
                reason="Confirmed local recovery",
            )

    def test_current_addon_runtime_cannot_take_over_its_own_record(self, tmp_path):
        def current_runtime(owner):
            return _local_runtime(
                owner,
                freecad_pid=owner.freecad_pid,
                freecad_process_started_at=owner.freecad_process_started_at,
                addon_runtime_id=owner.addon_runtime_id,
            )

        (
            _,
            _,
            _,
            _,
            local_document,
            service,
        ) = _foreign_recovery_setup(
            tmp_path,
            runtime_factory=current_runtime,
        )
        service.import_adjacent_foreign_recovery(
            local_document.session_uuid,
            live_document=local_document,
        )

        with pytest.raises(ForeignRecoveryError, match="current live addon runtime"):
            service.confirmed_takeover_foreign_recovery(
                local_document.session_uuid,
                live_document=local_document,
                confirmed=True,
                document_dirty=False,
                reason="Confirmed local recovery",
            )

    @pytest.mark.parametrize("proof", ["reboot", "missing-process", "pid-reuse"])
    def test_confirmed_takeover_fences_dead_owner_and_rebinds_local_document(
        self, tmp_path, proof
    ):
        def runtime_factory(owner):
            return _local_runtime(
                owner,
                boot_id="boot-b" if proof == "reboot" else owner.boot_id,
            )

        def probe(owner_pid):
            assert owner_pid == 10
            if proof == "missing-process":
                return ProcessLivenessEvidence(False)
            return ProcessLivenessEvidence(
                True,
                process_started_at="2026-07-22T00:03:00Z",
            )

        (
            model,
            _,
            grant,
            _,
            local_document,
            service,
        ) = _foreign_recovery_setup(
            tmp_path,
            runtime_factory=runtime_factory,
            process_liveness_probe=probe,
        )
        imported = service.import_adjacent_foreign_recovery(
            local_document.session_uuid,
            live_document=local_document,
        )

        taken = service.confirmed_takeover_foreign_recovery(
            local_document.session_uuid,
            live_document=local_document,
            confirmed=True,
            document_dirty=True,
            reason="Confirmed selected-document takeover",
        )

        persisted = service.sidecar_store.read(
            model.with_name(model.name + ".freecad-mcp.lock")
        )
        assert taken == persisted
        assert taken.state == LeaseState.USER_INTERVENED
        assert taken.document == local_document
        assert taken.document.session_uuid != imported["foreign_document_session_uuid"]
        assert taken.generation == grant.record.generation + 1
        assert taken.token_fingerprint != grant.record.token_fingerprint
        assert taken.user_intervened is True
        assert taken.dirty is True
        assert service.get_foreign_recovery(local_document.session_uuid) is None
        public = service.get_effective(local_document.session_uuid)
        assert public["lease"]["state"] == LeaseState.USER_INTERVENED.value
        assert "token_fingerprint" not in public
        assert grant.credential.token not in json.dumps(public)
        with pytest.raises(AuthorizationError):
            service.authorize(grant.credential)

    def test_takeover_is_cas_fenced_if_sidecar_changes_after_import(self, tmp_path):
        (
            model,
            _,
            _,
            foreign_service,
            local_document,
            service,
        ) = _foreign_recovery_setup(
            tmp_path,
            runtime_factory=lambda owner: _local_runtime(owner, boot_id="boot-b"),
        )
        service.import_adjacent_foreign_recovery(
            local_document.session_uuid,
            live_document=local_document,
        )
        sidecar = model.with_name(model.name + ".freecad-mcp.lock")
        current = foreign_service.sidecar_store.read(sidecar)
        changed = current.revised(current_operation="Concurrent owner update")
        foreign_service.sidecar_store.replace(
            sidecar,
            changed,
            expected=current,
        )

        with pytest.raises(CoordinationError, match="changed after import"):
            service.confirmed_takeover_foreign_recovery(
                local_document.session_uuid,
                live_document=local_document,
                confirmed=True,
                document_dirty=False,
                reason="Confirmed selected-document takeover",
            )

        assert foreign_service.sidecar_store.read(sidecar) == changed
        assert service.get(local_document.session_uuid) is None
        effective = service.get_effective(local_document.session_uuid)
        assert effective["coordination_lost"] is True
        assert effective["document_state"]["error"]["code"] == (
            "FOREIGN_AUTHORITY_CHANGED"
        )


@pytest.mark.unit
class TestDocumentLeaseLifecycle:
    def test_server_owned_mutation_transitions_and_heartbeat_metadata(
        self, saved_lease
    ):
        _, _, service, clock, grant = saved_lease
        credential = grant.credential
        heartbeat = service.heartbeat(
            credential, current_operation="Waiting", task_summary="Task"
        )
        assert heartbeat["lease"]["state"] == LeaseState.LOCKED_IDLE.value
        assert heartbeat["document_state"]["dirty"] is False
        with pytest.raises(TypeError):
            service.heartbeat(credential, state="LOCKED_ERROR")  # type: ignore[call-arg]

        editing = service.begin_mutation(credential, operation="Create Pad")
        assert editing.state == LeaseState.LOCKED_EDITING
        recomputing = service.begin_recompute(credential)
        assert recomputing.state == LeaseState.LOCKED_RECOMPUTING
        idle = service.complete_operation(credential, dirty=True)
        assert idle.state == LeaseState.LOCKED_IDLE
        assert idle.dirty is True
        assert idle.last_mutation_revision == 1

    def test_takeover_rotates_generation_and_revokes_owner(self, saved_lease):
        _, _, service, _, grant = saved_lease
        old = grant.credential
        taken = service.takeover(old.document_session_uuid, dirty=True)
        assert taken.state == LeaseState.USER_INTERVENED
        assert taken.generation == old.generation + 1
        assert taken.user_intervened
        with pytest.raises(AuthorizationError):
            service.authorize(old)
        with pytest.raises(AuthorizationError):
            service.heartbeat(
                replace(
                    old,
                    generation=taken.generation,
                    # Even knowing the new generation cannot reconstruct token.
                )
            )

    def test_local_keep_dirty_acknowledgement_remains_a_blocking_record(
        self, saved_lease
    ):
        model, _, service, _, grant = saved_lease
        taken = service.takeover(grant.credential.document_session_uuid, dirty=True)

        acknowledged = service.acknowledge_local_dirty(
            taken.document.session_uuid,
            document_dirty=True,
            reason="Confirmed in GUI",
        )

        assert acknowledged.state == LeaseState.UNLOCKED_DIRTY
        assert acknowledged.dirty is True
        assert acknowledged.error.code == "DIRTY_ACKNOWLEDGED"
        assert model.with_name(model.name + ".freecad-mcp.lock").exists()
        with pytest.raises(LeaseConflictError):
            service.acquire(taken.document.session_uuid, _owner())

    def test_keep_dirty_requires_takeover_and_live_dirty_state(self, saved_lease):
        _, _, service, _, grant = saved_lease
        with pytest.raises(LeaseStateError):
            service.acknowledge_local_dirty(
                grant.credential.document_session_uuid,
                document_dirty=True,
            )
        service.takeover(grant.credential.document_session_uuid, dirty=False)
        with pytest.raises(LocalRecoveryError):
            service.acknowledge_local_dirty(
                grant.credential.document_session_uuid,
                document_dirty=False,
            )

    def test_verified_local_save_cas_clears_taken_over_record(self, saved_lease):
        model, _, service, _, grant = saved_lease
        session_uuid = grant.credential.document_session_uuid
        service.takeover(session_uuid, dirty=True)
        model.write_bytes(b"locally saved and independently verified")
        verified = capture_file_baseline(model)

        terminal = service.complete_local_save_and_clear(
            session_uuid,
            verified_baseline=verified,
            baseline_validated=True,
            document_modified=False,
        )

        assert terminal["lease"]["state"] == LeaseState.UNLOCKED_SAVED.value
        assert service.get(session_uuid) is None
        assert not model.with_name(model.name + ".freecad-mcp.lock").exists()

    def test_local_save_clear_detects_post_verification_file_change(
        self, saved_lease, tmp_path, monkeypatch
    ):
        model, _, service, _, grant = saved_lease
        session_uuid = grant.credential.document_session_uuid
        service.takeover(session_uuid, dirty=True)
        verified = capture_file_baseline(model)
        replacement = tmp_path / "post-verification-replacement.FCStd"
        replacement.write_bytes(model.read_bytes())
        current = model.stat()
        os.utime(
            replacement,
            ns=(current.st_atime_ns, verified.mtime_ns),
        )
        os.replace(replacement, model)

        def forbidden_hash(*_args, **_kwargs):
            raise AssertionError("local CAS release attempted a full SHA-256")

        monkeypatch.setattr(
            lease_service_module, "capture_file_baseline", forbidden_hash
        )

        with pytest.raises(LocalRecoveryError, match="changed after verification"):
            service.complete_local_save_and_clear(
                session_uuid,
                verified_baseline=verified,
                baseline_validated=True,
                document_modified=False,
            )

        assert service.get(session_uuid)["lease"]["state"] == (
            LeaseState.USER_INTERVENED.value
        )
        assert model.with_name(model.name + ".freecad-mcp.lock").exists()

    def test_local_save_clear_requires_explicit_independent_validation(
        self, saved_lease
    ):
        model, _, service, _, grant = saved_lease
        session_uuid = grant.credential.document_session_uuid
        service.takeover(session_uuid, dirty=True)

        with pytest.raises(LocalRecoveryError, match="independent"):
            service.complete_local_save_and_clear(
                session_uuid,
                verified_baseline=capture_file_baseline(model),
                baseline_validated=False,
                document_modified=False,
            )

        assert service.get(session_uuid)["lease"]["state"] == (
            LeaseState.USER_INTERVENED.value
        )

    def test_stale_is_persisted_not_deleted_and_exact_owner_can_reconcile(
        self, saved_lease
    ):
        model, identities, service, clock, grant = saved_lease
        sidecar = model.with_name(model.name + ".freecad-mcp.lock")
        clock.advance(91)
        assert service.mark_expired_stale() == [grant.credential.document_session_uuid]
        assert sidecar.exists()
        assert (
            service.get(grant.credential.document_session_uuid)["lease"]["state"]
            == LeaseState.STALE.value
        )
        reconciled = service.reconcile_stale(
            grant.credential,
            validation=_validation(identities, grant.credential, modified=False),
        )
        assert reconciled.state == LeaseState.LOCKED_IDLE

    def test_stale_reconcile_rejects_changed_file_hash(self, saved_lease):
        model, identities, service, clock, grant = saved_lease
        clock.advance(91)
        service.mark_expired_stale()
        model.write_bytes(b"externally replaced archive")

        with pytest.raises(LiveDocumentValidationError) as caught:
            service.reconcile_stale(
                grant.credential,
                validation=_validation(identities, grant.credential),
            )

        assert "hash changed" in str(caught.value)
        status = service.get(grant.credential.document_session_uuid)
        assert status["lease"]["state"] == LeaseState.STALE.value
        assert status["document_state"]["error"]["code"] == (
            "LIVE_DOCUMENT_VALIDATION_FAILED"
        )

    def test_stale_reconcile_requires_fresh_validation(self, saved_lease):
        _, _, service, clock, grant = saved_lease
        clock.advance(91)
        service.mark_expired_stale()
        with pytest.raises(TypeError):
            service.reconcile_stale(grant.credential)  # type: ignore[call-arg]

    def test_heartbeat_disk_write_is_coalesced(self, saved_lease):
        model, _, service, clock, grant = saved_lease
        sidecar = model.with_name(model.name + ".freecad-mcp.lock")
        first_disk = json.loads(sidecar.read_text(encoding="utf-8"))
        service.heartbeat(grant.credential)
        second_disk = json.loads(sidecar.read_text(encoding="utf-8"))
        assert (
            second_disk["lease"]["heartbeat_sequence"]
            == first_disk["lease"]["heartbeat_sequence"]
        )
        clock.advance(31)
        service.heartbeat(grant.credential)
        third_disk = json.loads(sidecar.read_text(encoding="utf-8"))
        assert third_disk["lease"]["heartbeat_sequence"] == 2

    def test_error_blocks_normal_mutation_but_permits_save_recovery(self, saved_lease):
        _, _, service, _, grant = saved_lease
        service.begin_mutation(grant.credential, operation="Pad")
        error = service.record_error(
            grant.credential,
            code="PAD_FAILED",
            message="Pad did not recompute",
            dirty=True,
        )
        assert error.state == LeaseState.LOCKED_ERROR
        with pytest.raises(LeaseStateError):
            service.begin_mutation(grant.credential, operation="Pocket")
        assert service.begin_save(grant.credential).state == LeaseState.LOCKED_SAVING

    def test_error_allows_only_explicit_recovery_transition(self, saved_lease):
        _, _, service, _, grant = saved_lease
        service.begin_mutation(grant.credential, operation="Pad")
        service.record_error(
            grant.credential,
            code="PAD_FAILED",
            message="restore required",
            dirty=True,
        )

        recovery = service.begin_recovery(grant.credential, operation="restore")

        assert recovery.state == LeaseState.LOCKED_EDITING
        assert recovery.error is None
        assert recovery.validation_complete is False
        assert recovery.last_mutation_revision == 2

    def test_clean_release_requires_verified_current_save(self, saved_lease):
        model, identities, service, _, grant = saved_lease
        credential = grant.credential
        assert grant.record.validation_complete is True
        assert grant.record.baseline is not None
        service.begin_mutation(credential, operation="Pad")
        service.complete_operation(credential, dirty=True)
        with pytest.raises(CleanReleaseError):
            service.release_clean(
                credential,
                validation=_validation(identities, credential, modified=True),
            )
        service.begin_save(credential)
        service.mark_save_verified(credential)
        released = service.release_clean(
            credential,
            validation=_validation(identities, credential),
        )
        assert released["lease"]["state"] == LeaseState.UNLOCKED_SAVED.value
        assert service.get(credential.document_session_uuid) is None
        assert not model.with_name(model.name + ".freecad-mcp.lock").exists()

    def test_clean_release_rejects_external_change_after_verified_save(
        self, saved_lease
    ):
        model, identities, service, _, grant = saved_lease
        credential = grant.credential
        service.begin_save(credential)
        service.mark_save_verified(credential)
        model.write_bytes(b"changed after verification")

        with pytest.raises(LiveDocumentValidationError) as caught:
            service.release_clean(
                credential,
                validation=_validation(identities, credential),
            )

        assert "hash changed" in str(caught.value)
        status = service.get(credential.document_session_uuid)
        assert status["lease"]["state"] == LeaseState.LOCKED_ERROR.value
        assert status["document_state"]["error"]["code"] == (
            "LIVE_DOCUMENT_VALIDATION_FAILED"
        )
        assert model.with_name(model.name + ".freecad-mcp.lock").exists()

    def test_clean_release_rejects_unvalidated_baseline(self, saved_lease):
        _, identities, service, _, grant = saved_lease
        credential = grant.credential
        service.begin_save(credential)
        service.mark_save_verified(credential)
        evidence = _validation(identities, credential, baseline_validated=False)
        with pytest.raises(LiveDocumentValidationError):
            service.release_clean(credential, validation=evidence)

    def test_clean_release_rejects_live_document_path_change(
        self, saved_lease, tmp_path
    ):
        _, identities, service, _, grant = saved_lease
        credential = grant.credential
        service.begin_save(credential)
        service.mark_save_verified(credential)
        destination = tmp_path / "unexpected.FCStd"
        destination.write_bytes(b"valid archive")
        canonical, comparison = canonicalize_path(
            destination, platform=identities.platform
        )
        moved_identity = replace(
            identities.resolve(credential.document_session_uuid),
            canonical_path=canonical,
            comparison_key=comparison,
            file_identity=file_identity_for_path(
                destination, platform=identities.platform
            ),
        )
        evidence = LiveDocumentValidation(
            document=moved_identity,
            document_modified=False,
            baseline=capture_file_baseline(destination, platform=identities.platform),
            baseline_validated=True,
        )

        with pytest.raises(LiveDocumentValidationError) as caught:
            service.release_clean(credential, validation=evidence)
        assert "path changed" in str(caught.value)

    def test_clean_release_rejects_replaced_file_identity_with_same_content(
        self, saved_lease, tmp_path
    ):
        model, identities, service, _, grant = saved_lease
        credential = grant.credential
        service.begin_save(credential)
        service.mark_save_verified(credential)
        replacement = tmp_path / "replacement.FCStd"
        replacement.write_bytes(model.read_bytes())
        replacement.replace(model)

        with pytest.raises(LiveDocumentValidationError) as caught:
            service.release_clean(
                credential,
                validation=_validation(identities, credential),
            )
        assert "file identit" in str(caught.value)

    def test_unsaved_document_cannot_clean_release(self):
        identities = DocumentIdentityService()
        identity = identities.register(name="Unsaved")
        service = DocumentLeaseService(identities)
        grant = service.acquire(identity.session_uuid, _owner())
        with pytest.raises(CleanReleaseError):
            service.release_clean(
                grant.credential,
                validation=LiveDocumentValidation(
                    document=identity,
                    document_modified=False,
                    baseline=None,
                    baseline_validated=True,
                ),
            )

    def test_two_services_cannot_acquire_same_saved_file(self, tmp_path):
        model = tmp_path / "model.FCStd"
        model.write_bytes(b"archive")
        first_identities = DocumentIdentityService()
        second_identities = DocumentIdentityService()
        first = first_identities.register(name="Model", path=model)
        second = second_identities.register(name="Model", path=model)
        first_service = DocumentLeaseService(first_identities)
        second_service = DocumentLeaseService(second_identities)
        first_service.acquire(first.session_uuid, _owner(), snapshot_id=_uuid())
        with pytest.raises(LeaseConflictError):
            second_service.acquire(second.session_uuid, _owner())


@pytest.mark.unit
class TestSaveAsIdentityConsistency:
    def test_explicit_pre_mutation_cancel_removes_linkage_with_exact_cas(
        self, saved_lease, tmp_path
    ):
        source, _, service, _, grant = saved_lease
        destination = tmp_path / "destination.FCStd"
        destination_sidecar = destination.with_name(
            destination.name + ".freecad-mcp.lock"
        )

        service.begin_save(grant.credential)
        service.reserve_save_as(grant.credential, destination)
        cancelled = service.cancel_save_before_mutation(grant.credential)

        assert cancelled.state == LeaseState.LOCKED_IDLE
        assert cancelled.migration is None
        assert not destination_sidecar.exists()
        assert SidecarStore().read(
            source.with_name(source.name + ".freecad-mcp.lock")
        ).migration is None

    def test_typed_cancellation_rolls_back_exact_save_as_reservation_once(
        self, saved_lease, tmp_path
    ):
        source, _, service, _, grant = saved_lease
        destination = tmp_path / "cancelled-destination.FCStd"
        destination_sidecar = destination.with_name(
            destination.name + ".freecad-mcp.lock"
        )
        request_id = _uuid()

        service.begin_save(grant.credential)
        service.reserve_save_as(grant.credential, destination)
        cancelling = service.begin_cancellation(
            grant.credential,
            request_id=request_id,
            mutation_may_have_begun=False,
        )
        assert cancelling.state == LeaseState.CANCELLING

        completed = service.complete_cancellation(
            grant.credential,
            request_id=request_id,
            mutation_may_have_begun=False,
        )
        repeated = service.complete_cancellation(
            grant.credential,
            request_id=request_id,
            mutation_may_have_begun=False,
        )

        assert completed.state == LeaseState.LOCKED_IDLE
        assert repeated == completed
        assert not destination_sidecar.exists()
        assert SidecarStore().read(
            source.with_name(source.name + ".freecad-mcp.lock")
        ).migration is None

    def test_post_invocation_cancellation_keeps_save_as_recovery_records(
        self, saved_lease, tmp_path
    ):
        _, _, service, _, grant = saved_lease
        destination = tmp_path / "uncertain-destination.FCStd"
        destination_sidecar = destination.with_name(
            destination.name + ".freecad-mcp.lock"
        )
        request_id = _uuid()

        service.begin_save(grant.credential)
        service.reserve_save_as(grant.credential, destination)
        service.begin_cancellation(
            grant.credential,
            request_id=request_id,
            mutation_may_have_begun=True,
        )
        completed = service.complete_cancellation(
            grant.credential,
            request_id=request_id,
            mutation_may_have_begun=True,
            dirty=True,
        )

        assert completed.state == LeaseState.LOCKED_ERROR
        assert completed.error.code == "REQUEST_CANCELLED_AFTER_MUTATION"
        assert completed.dirty is True
        assert destination_sidecar.exists()

    def test_cancelled_acquisition_after_snapshot_retains_error_and_snapshot(
        self, tmp_path
    ):
        model = tmp_path / "acquiring.FCStd"
        model.write_bytes(b"archive")
        identities = DocumentIdentityService()
        identity = identities.register(name="Acquiring", path=model)
        service = DocumentLeaseService(identities)
        reservation = service.begin_acquisition(identity.session_uuid, _owner())
        snapshot_id = _uuid()

        retained = service.fail_acquisition_after_mutation(
            reservation.credential,
            request_id=_uuid(),
            message="cancelled during saveCopy",
            snapshot_id=snapshot_id,
        )

        assert retained.state == LeaseState.LOCKED_ERROR
        assert retained.snapshot_id == snapshot_id
        assert retained.error.code == "REQUEST_CANCELLED_AFTER_MUTATION"
        assert model.with_name(model.name + ".freecad-mcp.lock").exists()

    def test_reservation_survives_restart_as_two_correlated_foreign_records(
        self, saved_lease, tmp_path
    ):
        source, _, service, _, grant = saved_lease
        credential = grant.credential
        destination = tmp_path / "destination.FCStd"
        source_sidecar = source.with_name(source.name + ".freecad-mcp.lock")
        destination_sidecar = destination.with_name(
            destination.name + ".freecad-mcp.lock"
        )

        service.begin_save(credential)
        pending = service.reserve_save_as(credential, destination)
        source_record = SidecarStore().read(source_sidecar)
        destination_record = SidecarStore().read(destination_sidecar)

        assert source_record.migration is not None
        assert destination_record.migration is not None
        assert source_record.migration.role == SaveAsMigrationRole.SOURCE
        assert destination_record.migration.role == SaveAsMigrationRole.DESTINATION
        assert (
            source_record.migration.migration_id
            == destination_record.migration.migration_id
        )
        assert destination_record.document == pending.document
        assert destination_record.migration == pending.migration
        assert destination_record.record_revision == pending.record_revision

        # Simulate saveAs having written the destination and a subsequent
        # addon process importing both immutable recovery records.  The
        # destination reservation intentionally has no trusted post-save file
        # identity yet, but it remains safe to import as a blocking shadow.
        destination.write_bytes(b"saved destination")
        restarted_identities = DocumentIdentityService()
        restarted_source = restarted_identities.register(
            name="RecoveredSource", path=source
        )
        restarted_destination = restarted_identities.register(
            name="RecoveredDestination", path=destination
        )
        restarted = DocumentLeaseService(restarted_identities)
        source_status = restarted.import_adjacent_foreign_recovery(
            restarted_source.session_uuid,
            live_document=restarted_source,
        )
        destination_status = restarted.import_adjacent_foreign_recovery(
            restarted_destination.session_uuid,
            live_document=restarted_destination,
        )

        assert (
            source_status["migration"]["migration_id"]
            == destination_status["migration"]["migration_id"]
        )
        assert source_status["migration"]["role"] == "source"
        assert destination_status["migration"]["role"] == "destination"
        public = json.dumps(restarted.list_foreign_recoveries())
        assert "token_fingerprint" not in public
        assert credential.token not in public

    def test_source_link_cas_failure_retains_self_describing_destination(
        self, saved_lease, tmp_path, monkeypatch
    ):
        source, _, service, _, grant = saved_lease
        credential = grant.credential
        destination = tmp_path / "destination.FCStd"
        source_sidecar = source.with_name(source.name + ".freecad-mcp.lock")
        destination_sidecar = destination.with_name(
            destination.name + ".freecad-mcp.lock"
        )
        original_replace = service.sidecar_store.replace

        def fail_source_link(path, record, *, expected):
            if (
                str(path) == str(source_sidecar)
                and record.migration is not None
                and record.migration.role == SaveAsMigrationRole.SOURCE
            ):
                raise SidecarConflictError("simulated source linkage CAS failure")
            return original_replace(path, record, expected=expected)

        service.begin_save(credential)
        monkeypatch.setattr(service.sidecar_store, "replace", fail_source_link)
        with pytest.raises(CoordinationError):
            service.reserve_save_as(credential, destination)

        source_record = SidecarStore().read(source_sidecar)
        destination_record = SidecarStore().read(destination_sidecar)
        assert source_record.migration is None
        assert destination_record.migration is not None
        assert destination_record.migration.role == SaveAsMigrationRole.DESTINATION
        assert (
            destination_record.migration.source_comparison_key
            == source_record.document.comparison_key
        )
        assert destination_sidecar.exists()
        assert source_sidecar.exists()

    def test_source_removal_failure_retains_both_correlated_sidecars(
        self, saved_lease, tmp_path, monkeypatch
    ):
        source, _, service, _, grant = saved_lease
        credential = grant.credential
        destination = tmp_path / "destination.FCStd"
        source_sidecar = source.with_name(source.name + ".freecad-mcp.lock")
        destination_sidecar = destination.with_name(
            destination.name + ".freecad-mcp.lock"
        )

        service.begin_save(credential)
        service.reserve_save_as(credential, destination)
        destination.write_bytes(b"saved destination")
        original_delete = service.sidecar_store.delete

        def fail_source_delete(path, *, expected):
            if str(path) == str(source_sidecar):
                raise SidecarConflictError("simulated source CAS removal failure")
            return original_delete(path, expected=expected)

        monkeypatch.setattr(service.sidecar_store, "delete", fail_source_delete)
        with pytest.raises(CoordinationError):
            service.commit_save_as(
                credential,
                destination=destination,
                baseline=capture_file_baseline(destination),
            )

        source_record = SidecarStore().read(source_sidecar)
        destination_record = SidecarStore().read(destination_sidecar)
        assert source_record.migration is not None
        assert destination_record.migration is not None
        assert (
            source_record.migration.migration_id
            == destination_record.migration.migration_id
        )
        assert destination_record.state == LeaseState.LOCKED_ERROR
        assert source_sidecar.exists()
        assert destination_sidecar.exists()

    def test_destination_linkage_clear_failure_is_not_clean_success(
        self, saved_lease, tmp_path, monkeypatch
    ):
        source, _, service, _, grant = saved_lease
        credential = grant.credential
        destination = tmp_path / "destination.FCStd"
        source_sidecar = source.with_name(source.name + ".freecad-mcp.lock")
        destination_sidecar = destination.with_name(
            destination.name + ".freecad-mcp.lock"
        )

        service.begin_save(credential)
        service.reserve_save_as(credential, destination)
        destination.write_bytes(b"saved destination")
        original_replace = service.sidecar_store.replace

        def fail_linkage_clear(path, record, *, expected):
            if str(path) == str(destination_sidecar) and record.migration is None:
                raise SidecarConflictError(
                    "simulated destination linkage finalize failure"
                )
            return original_replace(path, record, expected=expected)

        monkeypatch.setattr(service.sidecar_store, "replace", fail_linkage_clear)
        with pytest.raises(CoordinationError):
            service.commit_save_as(
                credential,
                destination=destination,
                baseline=capture_file_baseline(destination),
            )

        persisted = SidecarStore().read(destination_sidecar)
        assert not source_sidecar.exists()
        assert persisted.state == LeaseState.LOCKED_ERROR
        assert persisted.migration is not None
        assert persisted.error is not None
        assert persisted.error.code == "SAVE_AS_LINKAGE_FINALIZE_FAILED"

    def test_live_inspection_does_not_silently_accept_path_change(self, tmp_path):
        source = tmp_path / "source.FCStd"
        destination = tmp_path / "destination.FCStd"
        source.write_bytes(b"source")
        destination.write_bytes(b"destination")

        class Document:
            Name = "Model"
            FileName = str(source)

        document = Document()
        identities = DocumentIdentityService()
        registered = identities.register_document(document)
        document.FileName = str(destination)

        observed = identities.inspect_registered_document(
            registered.session_uuid, document
        )
        authoritative = identities.resolve(registered.session_uuid)
        assert observed.comparison_key != authoritative.comparison_key
        assert authoritative.canonical_path == str(source.resolve())

    def test_failed_destination_promotion_does_not_publish_new_alias(
        self, saved_lease, tmp_path, monkeypatch
    ):
        source, identities, service, _, grant = saved_lease
        credential = grant.credential
        destination = tmp_path / "destination.FCStd"
        service.begin_save(credential)
        pending = service.reserve_save_as(credential, destination)
        destination.write_bytes(b"saved destination")
        destination_baseline = capture_file_baseline(destination)
        original_replace = service.sidecar_store.replace
        destination_sidecar = destination.with_name(
            destination.name + ".freecad-mcp.lock"
        )

        def fail_destination_promotion(path, record, *, expected):
            if str(path) == str(destination_sidecar) and expected == pending:
                raise SidecarConflictError("simulated destination CAS failure")
            return original_replace(path, record, expected=expected)

        monkeypatch.setattr(
            service.sidecar_store, "replace", fail_destination_promotion
        )
        with pytest.raises(CoordinationError):
            service.commit_save_as(
                credential,
                destination=destination,
                baseline=destination_baseline,
            )

        identity = identities.resolve(credential.document_session_uuid)
        assert identity.canonical_path == str(source.resolve())
        assert service.get(credential.document_session_uuid)["document"][
            "canonical_path"
        ] == str(source.resolve())
        assert source.with_name(source.name + ".freecad-mcp.lock").exists()
        assert destination_sidecar.exists()

    def test_successful_save_as_publishes_destination_before_source_removal(
        self, saved_lease, tmp_path
    ):
        source, identities, service, _, grant = saved_lease
        credential = grant.credential
        destination = tmp_path / "destination.FCStd"
        service.begin_save(credential)
        service.reserve_save_as(credential, destination)
        destination.write_bytes(b"saved destination")

        promoted = service.commit_save_as(
            credential,
            destination=destination,
            baseline=capture_file_baseline(destination),
        )

        identity = identities.resolve(credential.document_session_uuid)
        assert promoted.document == identity
        assert promoted.migration is None
        assert identity.canonical_path == str(destination.resolve())
        assert not source.with_name(source.name + ".freecad-mcp.lock").exists()
        destination_sidecar = destination.with_name(
            destination.name + ".freecad-mcp.lock"
        )
        assert destination_sidecar.exists()
        assert SidecarStore().read(destination_sidecar).migration is None
