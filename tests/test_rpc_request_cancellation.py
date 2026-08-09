"""Focused races for authenticated whole-request cancellation."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from types import SimpleNamespace

import pytest
from PySide import QtCore

from addon.FreeCADMCP.rpc_server.gui_dispatcher import GuiDispatcher, GuiTaskError
from addon.FreeCADMCP.rpc_server.inflight_requests import (
    InflightLeaseCredential,
    InflightRequestRegistry,
)
from addon.FreeCADMCP.rpc_server.lease_protocol import (
    RequestEnvelope,
    RequestReplayCache,
)
from addon.FreeCADMCP.rpc_server.rpc_server import _redact_rpc_diagnostic
from addon.FreeCADMCP.document_lease import (
    DocumentIdentityService,
    DocumentLeaseService,
    LocalRuntimeIdentity,
)
from addon.FreeCADMCP.rpc_server import rpc_server as rpc_server_module


def _uuid() -> str:
    return str(uuid.uuid4())


def _credential(token: str = "lease-secret-sentinel") -> InflightLeaseCredential:
    return InflightLeaseCredential(
        lease_id=_uuid(),
        document_session_uuid=_uuid(),
        generation=4,
        token=token,
        mcp_instance_id=_uuid(),
    )


@pytest.mark.unit
def test_foreign_session_cannot_observe_or_cancel_request():
    registry = InflightRequestRegistry()
    owner_session = _uuid()
    foreign_session = _uuid()
    request_id = _uuid()
    request = registry.register(
        owner_session,
        request_id,
        "create_object",
        (_credential(),),
        lease_affecting=True,
    )

    result = registry.request_cancel(foreign_session, request_id)

    assert result.status == "unknown"
    assert result.request is None
    assert request.token.snapshot().cancellation_requested is False


@pytest.mark.unit
def test_cancellation_resolution_is_claimed_and_cached_exactly_once():
    registry = InflightRequestRegistry()
    session_id = _uuid()
    request_id = _uuid()
    request = registry.register(
        session_id,
        request_id,
        "save_document_as",
        (_credential(),),
        lease_affecting=True,
    )
    assert registry.request_cancel(session_id, request_id).status == "requested"
    assert registry.request_cancel(session_id, request_id).status == "already_requested"

    claimed, cached = request.token.claim_cancellation_resolution()
    assert claimed is True
    assert cached is None
    expected = [{"state": "LOCKED_IDLE", "record_revision": 8}]
    request.token.finish_cancellation_resolution(expected)

    claimed_again, cached_again = request.token.claim_cancellation_resolution()
    assert claimed_again is False
    assert cached_again == expected
    cached_again[0]["state"] = "tampered"
    assert request.token.cancellation_resolution() == expected

    terminal = registry.finish_handler(session_id, request_id, status="cancelled")
    assert terminal.terminal is True
    assert registry.request_cancel(session_id, request_id).status == "completed"


@pytest.mark.unit
def test_concurrent_resolver_waits_for_authority_and_terminalizes_registry(
    monkeypatch,
):
    registry = InflightRequestRegistry()
    monkeypatch.setattr(
        rpc_server_module, "rpc_inflight_request_registry", registry
    )
    monkeypatch.setattr(rpc_server_module, "shutdown_requested", threading.Event())
    monkeypatch.setattr(rpc_server_module, "document_lease_service", None)
    session_id = _uuid()
    request_id = _uuid()
    credential = _credential()
    request = registry.register(
        session_id,
        request_id,
        "ping",
        (credential,),
    )
    registry.request_cancel(session_id, request_id)
    registry.finish_handler(session_id, request_id, status="failed")
    claimed, cached = request.token.claim_cancellation_resolution()
    assert claimed is True
    assert cached is None

    waiter_started = threading.Event()
    waiter_finished = threading.Event()
    observed = []

    def wait_for_owner():
        waiter_started.set()
        observed.append(
            rpc_server_module.FreeCADRPC()._complete_request_cancellation(request)
        )
        waiter_finished.set()

    waiter = threading.Thread(target=wait_for_owner)
    waiter.start()
    assert waiter_started.wait(1.0)
    assert waiter_finished.wait(0.05) is False

    expected = [{"state": "LOCKED_ERROR", "record_revision": 12}]
    rpc_server_module.FreeCADRPC._finish_cancellation_resolution(request, expected)
    waiter.join(timeout=1.0)

    assert waiter_finished.is_set()
    assert observed == [expected]
    status = registry.status(session_id, request_id)
    assert status.terminal is True
    assert status.terminal_status == "cancelled"
    assert registry.active_count == 0
    assert request.credentials == ()
    assert request.affected_credentials == ()


@pytest.mark.unit
def test_late_gui_cancellation_status_is_terminal_cancelled():
    registry = InflightRequestRegistry()
    session_id = _uuid()
    request_id = _uuid()
    request = registry.register(
        session_id,
        request_id,
        "create_object",
        (_credential(),),
        lease_affecting=True,
    )
    registry.begin_gui_phase(session_id, request_id, "gui:create_object")
    request.token.mark_mutation_started()
    registry.request_cancel(session_id, request_id)
    registry.finish_handler(session_id, request_id, status="failed")

    assert registry.end_gui_phase(session_id, request_id).terminal is False
    registry.finish_cancellation_resolution(
        request, [{"state": "LOCKED_ERROR", "dirty": True}]
    )

    status = registry.status(session_id, request_id)
    assert status.terminal is True
    assert status.terminal_status == "cancelled"
    assert registry.active_count == 0
    assert request.credentials == ()


@pytest.mark.unit
def test_irreversible_boundary_reports_not_cancellable_not_completed():
    registry = InflightRequestRegistry()
    session_id = _uuid()
    request_id = _uuid()
    request = registry.register(session_id, request_id, "release_document_lock")
    request.token.begin_irreversible("release_sidecar_cas")

    result = registry.request_cancel(session_id, request_id)

    assert result.status == "not_cancellable"
    assert result.request.phase == "release_sidecar_cas"
    assert result.request.terminal is False
    assert result.request.cancellation_requested is False


@pytest.mark.unit
def test_queued_gui_request_is_atomically_removed_before_execution():
    QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    registry = InflightRequestRegistry()
    dispatcher = GuiDispatcher()
    session_id = _uuid()
    request_id = _uuid()
    request = registry.register(session_id, request_id, "create_object")
    registry.begin_gui_phase(session_id, request_id, "gui:create_object")
    executed = []
    errors = []

    def submit():
        try:
            dispatcher.submit(
                lambda: executed.append(True),
                2.0,
                session_id=session_id,
                request_id=request_id,
                on_complete=lambda _request_id, _outcome: (
                    registry.end_gui_phase(session_id, request_id)
                ),
            )
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=submit)
    worker.start()
    deadline = time.monotonic() + 1.0
    while dispatcher.pending_count != 1 and time.monotonic() < deadline:
        time.sleep(0.001)

    assert registry.request_cancel(session_id, request_id).status == "requested"
    assert dispatcher.cancel_request(session_id, request_id) == "cancelled_pending"
    worker.join(timeout=1.0)

    assert executed == []
    assert len(errors) == 1 and isinstance(errors[0], GuiTaskError)
    assert dispatcher.pending_count == 0
    assert request.token.snapshot().active_gui_phases == 0


@pytest.mark.unit
def test_running_gui_request_is_signalled_but_never_claimed_stopped():
    QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    registry = InflightRequestRegistry()
    dispatcher = GuiDispatcher()
    session_id = _uuid()
    request_id = _uuid()
    request = registry.register(session_id, request_id, "create_object")
    registry.begin_gui_phase(session_id, request_id, "gui:create_object")
    started = threading.Event()
    release = threading.Event()

    def task():
        request.token.begin_mutation("gui_mutation_invocation")
        started.set()
        release.wait(1.0)
        return "actual-result"

    results = []
    submitter = threading.Thread(
        target=lambda: results.append(
            dispatcher.submit(
                task,
                2.0,
                session_id=session_id,
                request_id=request_id,
                on_complete=lambda _request_id, _outcome: (
                    registry.end_gui_phase(session_id, request_id)
                ),
            )
        )
    )
    submitter.start()
    deadline = time.monotonic() + 1.0
    while dispatcher.pending_count != 1 and time.monotonic() < deadline:
        time.sleep(0.001)
    drain = threading.Thread(target=dispatcher._drain_one)
    drain.start()
    assert started.wait(0.5)

    assert registry.request_cancel(session_id, request_id).status == "requested"
    assert dispatcher.cancel_request(session_id, request_id) == "running"
    assert request.token.snapshot().mutation_started is True

    release.set()
    drain.join(timeout=1.0)
    submitter.join(timeout=1.0)
    assert results == ["actual-result"]


@pytest.mark.unit
def test_persisted_diagnostic_redacts_exact_tokens_and_fingerprints():
    token = "lease-token-exact-sentinel"
    session_token = "session-token-exact-sentinel"
    fingerprint = "sha256:" + hashlib.sha256(token.encode()).hexdigest()
    registry = InflightRequestRegistry()
    request = registry.register(
        _uuid(),
        _uuid(),
        "create_object",
        (_credential(token),),
    )
    identity = {
        "rpc_session_token": session_token,
        "lease_credentials": [{"token": token}],
    }

    redacted = _redact_rpc_diagnostic(
        {"message": f"failure {token} {session_token} {fingerprint}"},
        identity=identity,
        inflight=request,
    )

    assert token not in redacted
    assert session_token not in redacted
    assert fingerprint not in redacted
    assert "<redacted>" in redacted


@pytest.mark.unit
def test_emitted_cancellation_error_deeply_redacts_exact_credential(monkeypatch):
    token = "cancellation-error-token-exact-sentinel"
    fingerprint = "sha256:" + hashlib.sha256(token.encode()).hexdigest()
    credential = _credential(token)
    registry = InflightRequestRegistry()
    monkeypatch.setattr(
        rpc_server_module, "rpc_inflight_request_registry", registry
    )
    monkeypatch.setattr(rpc_server_module, "shutdown_requested", threading.Event())

    class SecretError(RuntimeError):
        code = token

    class FailingService:
        @staticmethod
        def begin_cancellation(*_args, **_kwargs):
            raise SecretError(
                {"nested": [{"token": token}, {"fingerprint": fingerprint}]}
            )

    monkeypatch.setattr(
        rpc_server_module, "document_lease_service", FailingService()
    )
    request = registry.register(
        _uuid(),
        _uuid(),
        "create_object",
        (credential,),
        lease_affecting=True,
    )
    request.touch_credentials((credential,))
    request.token.request_cancel()

    emitted = rpc_server_module.FreeCADRPC()._complete_request_cancellation(request)
    rendered = json.dumps(emitted, sort_keys=True)

    assert token not in rendered
    assert fingerprint not in rendered
    assert "<redacted>" in rendered


@pytest.mark.unit
def test_cancellation_touches_only_credentials_used_by_request(monkeypatch):
    first = _credential("touched-secret")
    second = _credential("untouched-secret")
    registry = InflightRequestRegistry()
    monkeypatch.setattr(
        rpc_server_module, "rpc_inflight_request_registry", registry
    )
    monkeypatch.setattr(rpc_server_module, "shutdown_requested", threading.Event())
    calls = []

    class Record:
        def __init__(self, document_session_uuid):
            self.document_session_uuid = document_session_uuid

        def to_public_dict(self):
            return {"document_session_uuid": self.document_session_uuid}

    class RecordingService:
        @staticmethod
        def begin_cancellation(credential, **_kwargs):
            calls.append(("begin", credential.document_session_uuid))
            return Record(credential.document_session_uuid)

        @staticmethod
        def complete_cancellation(credential, **_kwargs):
            calls.append(("complete", credential.document_session_uuid))
            return Record(credential.document_session_uuid)

    monkeypatch.setattr(
        rpc_server_module, "document_lease_service", RecordingService()
    )
    request = registry.register(
        _uuid(),
        _uuid(),
        "create_object",
        (first, second),
        lease_affecting=True,
    )
    request.touch_credentials((first,))
    request.token.request_cancel()

    rpc_server_module.FreeCADRPC()._complete_request_cancellation(request)

    assert calls
    assert {session_uuid for _phase, session_uuid in calls} == {
        first.document_session_uuid
    }
    assert second.document_session_uuid not in {
        session_uuid for _phase, session_uuid in calls
    }


@pytest.mark.unit
def test_shutdown_skips_wedged_begin_owner_and_retains_fail_closed_fence(
    monkeypatch,
):
    registry = InflightRequestRegistry()
    credential = _credential()
    request = registry.register(
        _uuid(),
        _uuid(),
        "create_object",
        (credential,),
        lease_affecting=True,
    )
    request.touch_credentials((credential,))
    request.token.request_cancel()
    assert request.token.claim_cancellation_begin() is True

    class Server:
        def __init__(self):
            self.calls = []

        def begin_shutdown(self):
            self.calls.append("begin_shutdown")

        def shutdown(self):
            self.calls.append("shutdown")

        def server_close(self):
            self.calls.append("server_close")

    class ForbiddenService:
        @staticmethod
        def begin_cancellation(*_args, **_kwargs):
            raise AssertionError("shutdown must not interleave cancellation")

    server = Server()
    stop_event = threading.Event()
    monkeypatch.setattr(
        rpc_server_module, "rpc_inflight_request_registry", registry
    )
    monkeypatch.setattr(rpc_server_module, "rpc_server_instance", server)
    monkeypatch.setattr(rpc_server_module, "rpc_server_thread", None)
    monkeypatch.setattr(rpc_server_module, "gui_dispatcher", None)
    monkeypatch.setattr(rpc_server_module, "worker_manager", None)
    monkeypatch.setattr(
        rpc_server_module, "document_lease_service", ForbiddenService()
    )
    monkeypatch.setattr(rpc_server_module, "shutdown_requested", stop_event)
    monkeypatch.setattr(
        rpc_server_module, "RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS", 0.02
    )
    for name in (
        "rpc_server_runtime_id",
        "rpc_server_started_at",
        "rpc_server_actual_endpoint",
        "rpc_session_manager",
        "rpc_request_replay_cache",
        "rpc_runtime_manifest",
    ):
        monkeypatch.setattr(rpc_server_module, name, getattr(rpc_server_module, name))

    started_at = time.monotonic()
    result = rpc_server_module.stop_rpc_server()
    elapsed = time.monotonic() - started_at

    assert result == "RPC Server stopped."
    assert elapsed < 0.5
    assert server.calls == ["begin_shutdown", "shutdown", "server_close"]
    assert stop_event.is_set()
    assert registry.active_count == 1
    assert request.token.snapshot().terminal is False
    assert request.token.snapshot().cancellation_resolved is False
    assert request.credentials == (credential,)


@pytest.mark.unit
def test_acquisition_cancelled_in_hash_gap_aborts_private_reservation(
    tmp_path, monkeypatch
):
    model = tmp_path / "hash-gap.FCStd"
    model.write_bytes(b"stable archive")
    identities = DocumentIdentityService()
    identity = identities.register(name="HashGap", path=model)
    runtime_id = _uuid()
    profile_id = _uuid()
    service = DocumentLeaseService(
        identities,
        local_runtime_identity=LocalRuntimeIdentity(
            addon_profile_id=profile_id,
            addon_runtime_id=runtime_id,
            freecad_pid=100,
            freecad_process_started_at="2026-07-22T00:00:00Z",
            boot_id="boot-test",
            hostname="localhost",
        ),
    )
    document = SimpleNamespace(
        Name="HashGap",
        FileName=str(model),
        Modified=False,
        Objects=[],
    )
    monkeypatch.setattr(rpc_server_module, "document_identity_service", identities)
    monkeypatch.setattr(rpc_server_module, "document_lease_service", service)
    monkeypatch.setattr(
        rpc_server_module,
        "rpc_runtime_manifest",
        SimpleNamespace(
            profile_id=profile_id,
            addon_runtime_id=runtime_id,
            freecad_pid=100,
            freecad_process_started_at="2026-07-22T00:00:00Z",
            boot_id="boot-test",
        ),
    )
    monkeypatch.setattr(
        rpc_server_module,
        "_live_document_from_selector",
        lambda _selector: (document, identity),
    )
    rpc = rpc_server_module.FreeCADRPC()
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, timeout=None: task())
    registry = InflightRequestRegistry()
    monkeypatch.setattr(
        rpc_server_module, "rpc_inflight_request_registry", registry
    )
    session_id = _uuid()
    request_id = _uuid()
    inflight = registry.register(
        session_id,
        request_id,
        "acquire_document_lock",
        lease_affecting=True,
    )
    hash_started = threading.Event()
    release_hash = threading.Event()
    lease_package = rpc_server_module._import_document_lease()
    original_capture = lease_package.capture_file_baseline

    def blocking_capture(path, *, platform=None):
        hash_started.set()
        release_hash.wait(2.0)
        return original_capture(path, platform=platform)

    monkeypatch.setattr(lease_package, "capture_file_baseline", blocking_capture)
    failures = []

    def acquire():
        rpc._inflight_context.value = inflight
        try:
            rpc._acquire_document_lock_v2(
                {"document_session_uuid": identity.session_uuid},
                request_identity={
                    "request_id": request_id,
                    "instance_id": _uuid(),
                    "pid": 200,
                    "mcp_process_started_at": "2026-07-22T00:00:01Z",
                    "client": "pytest",
                    "agent_id": "agent",
                },
                task_description="hash gap",
                client="pytest",
                agent_id="agent",
                hash_policy="sha256",
            )
        except BaseException as exc:
            failures.append(exc)
        finally:
            del rpc._inflight_context.value

    worker = threading.Thread(target=acquire)
    worker.start()
    assert hash_started.wait(1.0)
    assert inflight.token.request_cancel()[0] is True
    release_hash.set()
    worker.join(timeout=2.0)

    assert len(failures) == 1
    assert failures[0].__class__.__name__ == "RequestCancellationError"
    assert service.get(identity.session_uuid) is None
    assert not model.with_name(model.name + ".freecad-mcp.lock").exists()
    assert inflight.token.snapshot().mutation_started is False
    assert inflight.token.cancellation_resolution()[0]["rolled_back"] is True


@pytest.mark.unit
def test_cancel_race_before_replay_publish_is_monotonic_and_idempotent(monkeypatch):
    session_id = _uuid()
    runtime_id = _uuid()
    request_id = _uuid()
    envelope = RequestEnvelope(
        request_id=request_id,
        session_token="session-secret",
        method="ping",
        params={},
        mcp_runtime_id=runtime_id,
    )
    session = SimpleNamespace(
        session_id=session_id,
        mcp=SimpleNamespace(
            runtime_id=runtime_id,
            client_build_id="pytest",
            pid=123,
            hostname="localhost",
            process_started_at="2026-07-22T00:00:00Z",
        ),
    )

    class Manager:
        @staticmethod
        def authenticate_envelope(_payload, *, transport_mcp_runtime_id=None):
            del transport_mcp_runtime_id
            return session, envelope

    replay = RequestReplayCache()
    monkeypatch.setattr(rpc_server_module, "rpc_session_manager", Manager())
    monkeypatch.setattr(rpc_server_module, "rpc_request_replay_cache", replay)
    monkeypatch.setattr(rpc_server_module, "rpc_server_runtime_id", _uuid())
    monkeypatch.setattr(rpc_server_module, "document_lease_service", None)

    class CancelOnResultInspection(dict):
        fired = False

        def get(self, key, default=None):
            if key in {"success", "ok"} and not self.fired:
                self.fired = True
                rpc_server_module.rpc_inflight_request_registry.request_cancel(
                    session_id, request_id
                )
            return super().get(key, default)

    class RacingRPC(rpc_server_module.FreeCADRPC):
        dispatch_count = 0

        def _dispatch(self, method, params):
            del method, params
            self.dispatch_count += 1
            return CancelOnResultInspection(success=True, marker="must-not-publish")

    rpc = RacingRPC()
    payload = {"request_id": request_id}
    first = rpc.invoke_v2(payload)
    cached = replay.status(runtime_id, request_id)
    second = rpc.invoke_v2(payload)

    assert first["ok"] is False
    assert first["result"]["error_code"] == "REQUEST_CANCELLED"
    assert "must-not-publish" not in str(first)
    assert cached.status == "completed"
    assert cached.response == first
    assert second == first
    assert rpc.dispatch_count == 1
    request_status = rpc_server_module.rpc_inflight_request_registry.status(
        session_id, request_id
    )
    assert request_status.terminal is True
    assert request_status.terminal_status == "cancelled"
