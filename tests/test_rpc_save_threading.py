"""Thread-affinity tests for the typed RPC save lifecycle."""

from __future__ import annotations

import json
import threading
import uuid
import zipfile
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.document_lease import (
    DocumentIdentity,
    DocumentIdentityService,
    DocumentLeaseService,
    LeaseCredential,
    LeaseState,
    LocalRuntimeIdentity,
    canonicalize_path,
    capture_file_baseline,
    file_identity_for_path,
)
from addon.FreeCADMCP.rpc_server import rpc_server
from addon.FreeCADMCP.rpc_server.save_service import (
    SaveService,
    verify_fcstd_archive,
)


def _write_fcstd(path, marker: str) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Document.xml", f"<Document marker='{marker}' />")
        archive.writestr("GuiDocument.xml", "<GuiDocument />")


class _Document:
    def __init__(self, name, path):
        self.Name = name
        self.FileName = str(path)
        self.Modified = True
        self.Objects = []
        self.save_thread = None
        self.save_as_thread = None

    def save(self):
        self.save_thread = threading.get_ident()
        _write_fcstd(self.FileName, "saved")
        self.Modified = False

    def saveAs(self, destination):
        self.save_as_thread = threading.get_ident()
        _write_fcstd(destination, "saved-as")
        self.FileName = destination
        self.Modified = False


class _Record(SimpleNamespace):
    def to_public_dict(self):
        return {
            "lease": {"state": self.state.value},
            "document_state": {"dirty": bool(getattr(self, "dirty", False))},
        }


class _LeaseService:
    def __init__(self, baseline, events, identity):
        self.events = events
        self.idle = _Record(
            baseline=baseline,
            document=identity,
            state=LeaseState.LOCKED_IDLE,
            state_revision=4,
            last_mutation_revision=2,
            last_verified_save_revision=2,
            validation_complete=True,
            dirty=True,
        )
        self.saving = _Record(
            baseline=baseline,
            document=identity,
            state=LeaseState.LOCKED_SAVING,
            state_revision=5,
            last_mutation_revision=2,
            last_verified_save_revision=1,
            validation_complete=False,
            dirty=True,
        )
        self.verified = _Record(
            baseline=baseline,
            document=identity,
            state=LeaseState.LOCKED_IDLE,
            state_revision=6,
            last_mutation_revision=2,
            last_verified_save_revision=2,
            validation_complete=True,
            dirty=False,
        )
        self.destination_reserved = False
        self.destination_committed = False
        self.save_cancelled = False
        self.error_recorded = False

    def authorize(self, _credential, *, selector, allowed_states):
        del selector
        self.events.append(("authorize", threading.get_ident()))
        if LeaseState.LOCKED_SAVING in allowed_states:
            return self.saving
        return self.idle

    def begin_save(self, _credential):
        self.events.append(("begin-save", threading.get_ident()))
        return self.saving

    def cancel_save_before_mutation(self, _credential):
        self.save_cancelled = True
        self.events.append(("cancel-save", threading.get_ident()))
        return self.idle

    def reserve_save_as(self, _credential, _destination):
        self.destination_reserved = True
        self.events.append(("reserve-save-as", threading.get_ident()))
        return self.saving

    def commit_save_as(self, _credential, *, destination, baseline):
        del destination, baseline
        self.destination_committed = True
        self.events.append(("commit-save-as", threading.get_ident()))
        return self.verified

    def mark_save_verified(self, _credential, *, baseline):
        self.verified.baseline = baseline
        self.events.append(("mark-verified", threading.get_ident()))
        return self.verified

    def record_error(self, _credential, **_details):
        self.error_recorded = True
        self.events.append(("record-error", threading.get_ident()))
        return _Record(
            baseline=self.saving.baseline,
            state=LeaseState.LOCKED_ERROR,
            state_revision=6,
            last_mutation_revision=2,
            dirty=True,
        )

    def release_clean(self, _credential, *, validation):
        assert validation.baseline == self.idle.baseline
        assert validation.baseline_validated is True
        assert validation.document_modified is False
        self.events.append(("release-clean", threading.get_ident()))
        return {
            "lease": {"state": "UNLOCKED_SAVED"},
            "document_state": {"snapshot_id": None},
        }


class _IdentityService:
    platform = None

    def __init__(self, identity, events):
        self.identity = identity
        self.events = events

    def inspect_registered_document(self, session_uuid, document):
        assert session_uuid == self.identity.session_uuid
        self.events.append(("identity-revalidate", threading.get_ident()))
        canonical, comparison = canonicalize_path(document.FileName)
        return DocumentIdentity(
            session_uuid=session_uuid,
            name=document.Name,
            canonical_path=canonical,
            comparison_key=comparison,
            file_identity=file_identity_for_path(canonical),
        )


class _DocumentLock:
    def __init__(self, events):
        self.events = events

    @staticmethod
    def get_request_identity():
        return {
            "request_id": "save-request",
            "authenticated_session_id": "rpc-session",
            "instance_id": "11111111-1111-4111-8111-111111111111",
            "pid": 101,
            "mcp_process_started_at": "2026-07-22T00:00:01Z",
            "host": "localhost",
        }

    @staticmethod
    def is_enabled():
        return True

    def begin_agent_mutation_scope(self, request_id, document_keys):
        assert request_id == "save-request"
        assert document_keys
        self.events.append(("marker-begin", threading.get_ident()))
        return True

    def end_agent_mutation_scope(self, request_id, document_keys):
        assert request_id == "save-request"
        assert document_keys
        self.events.append(("marker-end", threading.get_ident()))
        return True


class _TrackingSaveService(SaveService):
    def __init__(self, *, events, baseline_reader, archive_verifier):
        super().__init__(
            baseline_reader=baseline_reader,
            archive_verifier=archive_verifier,
        )
        self.events = events

    def invoke_save_gui(self, *args, **kwargs):
        self.events.append(("invoke-save", threading.get_ident()))
        return super().invoke_save_gui(*args, **kwargs)

    def invoke_save_as_gui(self, *args, **kwargs):
        self.events.append(("invoke-save-as", threading.get_ident()))
        return super().invoke_save_as_gui(*args, **kwargs)

    def verify_saved_file(self, *args, **kwargs):
        self.events.append(("verify-saved-file", threading.get_ident()))
        return super().verify_saved_file(*args, **kwargs)

    def revalidate_saved_document_gui(self, *args, **kwargs):
        self.events.append(("final-document-revalidation", threading.get_ident()))
        return super().revalidate_saved_document_gui(*args, **kwargs)


def _threaded_gui_dispatcher(gui_thread_ids):
    def dispatch(task, timeout=None):
        del timeout
        result = []
        failure = []

        def run():
            gui_thread_ids.append(threading.get_ident())
            try:
                result.append(task())
            except BaseException as exc:  # propagate the mocked Qt failure
                failure.append(exc)

        thread = threading.Thread(target=run, name="mock-freecad-gui")
        thread.start()
        thread.join()
        if failure:
            raise failure[0]
        return result[0]

    return dispatch


def _configure_rpc_test(monkeypatch, tmp_path):
    path = tmp_path / "model.FCStd"
    _write_fcstd(path, "baseline")
    baseline = capture_file_baseline(path)
    canonical, comparison = canonicalize_path(path)
    identity = DocumentIdentity(
        session_uuid="document-session",
        name="Model",
        canonical_path=canonical,
        comparison_key=comparison,
        file_identity=baseline.file_identity,
    )
    credential = LeaseCredential(
        lease_id="lease-id",
        document_session_uuid=identity.session_uuid,
        generation=1,
        token="secret-token",
        mcp_instance_id="mcp-runtime",
    )
    document = _Document(identity.name, canonical)
    events = []
    gui_thread_ids = []
    lease_service = _LeaseService(baseline, events, identity)
    identity_service = _IdentityService(identity, events)

    baseline_threads = []

    def baseline_reader(saved_path, *, platform=None):
        baseline_threads.append(threading.get_ident())
        return capture_file_baseline(saved_path, platform=platform)

    archive_threads = []

    def archive_verifier(saved_path):
        archive_threads.append(threading.get_ident())
        return verify_fcstd_archive(saved_path)

    service = _TrackingSaveService(
        events=events,
        baseline_reader=baseline_reader,
        archive_verifier=archive_verifier,
    )
    rpc = rpc_server.FreeCADRPC()
    monkeypatch.setattr(rpc, "_dispatch_gui", _threaded_gui_dispatcher(gui_thread_ids))
    monkeypatch.setattr(rpc_server, "document_lease_service", lease_service)
    monkeypatch.setattr(rpc_server, "document_identity_service", identity_service)
    monkeypatch.setattr(rpc_server, "save_service", service)
    monkeypatch.setattr(
        rpc_server,
        "_credential_for_selector",
        lambda _selector, _request_identity: (credential, identity, document),
    )
    monkeypatch.setattr(
        rpc_server, "_import_document_lock", lambda: _DocumentLock(events)
    )
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "getDocument",
        lambda name: document if name == document.Name else None,
    )
    return SimpleNamespace(
        rpc=rpc,
        path=path,
        document=document,
        events=events,
        gui_thread_ids=gui_thread_ids,
        baseline_threads=baseline_threads,
        archive_threads=archive_threads,
        lease_service=lease_service,
    )


@pytest.mark.unit
def test_post_save_validation_runs_on_rpc_caller_not_gui_thread(tmp_path, monkeypatch):
    context = _configure_rpc_test(monkeypatch, tmp_path)
    caller_thread = threading.get_ident()
    worker_threads = []

    def worker_validator(_path, _document_name, _profile, _expected):
        worker_threads.append(threading.get_ident())
        return {"ok": True, "worker_reopened": True}

    monkeypatch.setattr(rpc_server, "_validate_saved_document_worker", worker_validator)

    result = context.rpc.save_document({"document_session_uuid": "document-session"})

    assert result["success"] is True
    assert context.document.save_thread in context.gui_thread_ids
    # Compare-before-save and both post-save captures, plus the ZIP read and
    # FreeCADCmd/domain validator, stay off Qt on the XML-RPC caller thread.
    assert context.baseline_threads == [
        caller_thread,
        caller_thread,
        caller_thread,
    ]
    assert context.archive_threads == [caller_thread]
    assert worker_threads == [caller_thread]
    event_threads = dict(context.events)
    assert event_threads["verify-saved-file"] == caller_thread
    assert event_threads["final-document-revalidation"] in context.gui_thread_ids
    assert event_threads["mark-verified"] in context.gui_thread_ids
    assert context.lease_service.error_recorded is False


@pytest.mark.unit
def test_failed_save_as_validation_keeps_reservation_and_records_gui_error(
    tmp_path, monkeypatch
):
    context = _configure_rpc_test(monkeypatch, tmp_path)
    destination = tmp_path / "destination.FCStd"

    monkeypatch.setattr(
        rpc_server,
        "_validate_saved_document_worker",
        lambda *_args: {"ok": False, "reason": "Body.Tip mismatch"},
    )

    result = context.rpc.save_document_as(
        {"document_session_uuid": "document-session"}, str(destination)
    )

    assert result["success"] is False
    assert result["error_code"] == "SAVE_DOMAIN_VALIDATION_FAILED"
    assert context.lease_service.destination_reserved is True
    assert context.lease_service.destination_committed is False
    assert context.lease_service.save_cancelled is False
    assert context.lease_service.error_recorded is True
    assert destination.exists()
    event_threads = dict(context.events)
    assert event_threads["record-error"] in context.gui_thread_ids
    assert "final-document-revalidation" not in event_threads


@pytest.mark.unit
def test_clean_release_reuses_verified_baseline_without_gui_hash(tmp_path, monkeypatch):
    context = _configure_rpc_test(monkeypatch, tmp_path)
    context.document.Modified = False
    lease_module = rpc_server._import_document_lease()

    def forbidden_hash(*_args, **_kwargs):
        raise AssertionError("clean release attempted a full SHA-256 on Qt")

    monkeypatch.setattr(lease_module, "capture_file_baseline", forbidden_hash)

    result = context.rpc.release_document_lock(
        selector={"document_session_uuid": "document-session"},
        disposition="saved",
    )

    assert result["success"] is True
    event_threads = dict(context.events)
    assert event_threads["release-clean"] in context.gui_thread_ids


@pytest.mark.unit
def test_finalize_rejects_unknown_save_mode_before_any_document_write():
    rpc = rpc_server.FreeCADRPC()

    result = rpc.finalize_document_edit(
        {"document_session_uuid": "document-session"},
        save_mode="silently-save-anyway",
    )

    assert result == {
        "success": False,
        "error_code": "INVALID_SAVE_MODE",
        "error": "save_mode must be save, save_as, or first_save",
    }


@pytest.mark.unit
def test_saved_acquisition_reserves_before_caller_hash_and_gui_snapshot(
    tmp_path, monkeypatch
):
    model = tmp_path / "acquire.FCStd"
    _write_fcstd(model, "acquire")
    document = _Document("Acquire", model)
    document.Modified = False
    identities = DocumentIdentityService()
    identity = identities.register_document(document)
    sidecar = model.with_name(model.name + ".freecad-mcp.lock")
    caller_thread = threading.get_ident()
    gui_thread_ids = []
    events = []
    lease_module = rpc_server._import_document_lease()
    original_capture = lease_module.capture_file_baseline

    def capture_after_reservation(path, *, platform=None):
        events.append(("hash", threading.get_ident()))
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        assert payload["lease"]["state"] == LeaseState.ACQUIRING.value
        return original_capture(path, platform=platform)

    snapshot_id = str(uuid.uuid4())

    def snapshot_after_reservation(snapshot_document):
        assert snapshot_document is document
        events.append(("snapshot", threading.get_ident()))
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        assert payload["lease"]["state"] == LeaseState.ACQUIRING.value
        return snapshot_id

    manifest = SimpleNamespace(
        profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=202,
        freecad_process_started_at="2026-07-22T00:00:00Z",
        boot_id="boot-test",
    )
    service = DocumentLeaseService(
        identities,
        local_runtime_identity=LocalRuntimeIdentity(
            addon_profile_id=manifest.profile_id,
            addon_runtime_id=manifest.addon_runtime_id,
            freecad_pid=manifest.freecad_pid,
            freecad_process_started_at=manifest.freecad_process_started_at,
            boot_id=manifest.boot_id,
            hostname=rpc_server.platform.node(),
        ),
    )
    rpc = rpc_server.FreeCADRPC()
    monkeypatch.setattr(rpc, "_dispatch_gui", _threaded_gui_dispatcher(gui_thread_ids))
    monkeypatch.setattr(rpc_server, "document_lease_service", service)
    monkeypatch.setattr(rpc_server, "document_identity_service", identities)
    monkeypatch.setattr(rpc_server, "rpc_runtime_manifest", manifest)
    monkeypatch.setattr(
        rpc_server,
        "_live_document_from_selector",
        lambda _selector: (document, identity),
    )
    monkeypatch.setattr(
        rpc_server, "_import_document_lock", lambda: _DocumentLock(events)
    )
    monkeypatch.setattr(
        rpc_server.FreeCAD,
        "getDocument",
        lambda name: document if name == document.Name else None,
    )
    monkeypatch.setattr(
        lease_module, "capture_file_baseline", capture_after_reservation
    )
    monkeypatch.setattr(
        rpc_server,
        "create_lease_baseline_snapshot_gui",
        snapshot_after_reservation,
    )

    result = rpc.acquire_document_lock(
        selector={"document_session_uuid": identity.session_uuid}
    )

    assert result["success"] is True
    event_threads = dict(events)
    assert event_threads["hash"] == caller_thread
    assert event_threads["snapshot"] in gui_thread_ids
    assert result["lease"]["state"] == LeaseState.LOCKED_IDLE.value
    assert result["document_state"]["snapshot_id"] == snapshot_id
