"""Request-id guarantees at the authenticated native RPC boundary."""

from __future__ import annotations

import copy
import threading
import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.dispatch.gui_core import GuiDispatchCore
from addon.FreeCADMCP.rpc_server import request_identity
from addon.FreeCADMCP.rpc_server import rpc_server as addon_rpc
from addon.FreeCADMCP.rpc_server.inflight_requests import InflightRequestRegistry
from addon.FreeCADMCP.rpc_server.lease_protocol import (
    RequestEnvelope,
    RequestReplayCache,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.core_ops.object_ops import create_object_operation
from tests.helpers.native_readiness import attach_native_readiness


def _uuid() -> str:
    return str(uuid.uuid4())


class _SessionManager:
    def __init__(self, runtime_id: str):
        self.runtime_id = runtime_id
        self.session_ids: dict[str, str] = {}

    def authenticate_envelope(self, payload, *, transport_mcp_runtime_id=None):
        envelope = RequestEnvelope.from_dict(payload)
        assert transport_mcp_runtime_id == self.runtime_id
        assert envelope.mcp_runtime_id == self.runtime_id
        session_id = self.session_ids.setdefault(envelope.session_token, _uuid())
        return (
            SimpleNamespace(
                session_id=session_id,
                mcp=SimpleNamespace(
                    runtime_id=self.runtime_id,
                    client_build_id="pytest-idempotency",
                    pid=4321,
                    hostname="localhost",
                    process_started_at="2026-07-22T00:00:00Z",
                ),
            ),
            envelope,
        )


class _CountingRPC(addon_rpc.FreeCADRPC):
    def __init__(self, result=None, *, error: Exception | None = None):
        super().__init__()
        self.dispatch_count = 0
        self.result = result or {"success": True, "marker": "applied-once"}
        self.error = error

    def _dispatch(self, method, params):
        del method, params
        self.dispatch_count += 1
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.result)


@pytest.fixture
def _rpc_runtime(monkeypatch):
    runtime_id = _uuid()
    manager = _SessionManager(runtime_id)
    replay = RequestReplayCache()
    registry = InflightRequestRegistry()
    monkeypatch.setattr(addon_rpc, "rpc_session_manager", manager)
    monkeypatch.setattr(addon_rpc, "rpc_request_replay_cache", replay)
    monkeypatch.setattr(addon_rpc, "rpc_inflight_request_registry", registry)
    monkeypatch.setattr(addon_rpc, "rpc_server_runtime_id", _uuid())
    request_identity.set_request_identity(instance_id=runtime_id)
    try:
        yield runtime_id, manager, replay
    finally:
        request_identity.clear_request_identity()


def _credential(token: str, *, generation: int = 1) -> dict[str, object]:
    return {
        "lease_id": _uuid(),
        "document_session_uuid": _uuid(),
        "generation": generation,
        "token": token,
    }


def _envelope(
    runtime_id: str,
    *,
    request_id: str,
    session_token: str,
    method: str = "create_object",
    params: dict | None = None,
    credentials: list[dict[str, object]] | None = None,
) -> dict:
    return {
        "protocol_version": 2,
        "request_id": request_id,
        "session_token": session_token,
        "mcp_runtime_id": runtime_id,
        "method": method,
        "params": params
        or {
            "doc_name": "Model",
            "obj_data": {"Type": "Part::Feature", "Name": "Once"},
        },
        "lease_credentials": credentials if credentials is not None else [],
        "operation": {"name": "Idempotency test", "task_id": _uuid()},
    }


@pytest.mark.unit
def test_legacy_document_credentials_are_rejected_before_dispatch(_rpc_runtime):
    runtime_id, _manager, replay = _rpc_runtime
    request_id = _uuid()
    rpc = _CountingRPC()

    result = rpc.invoke_v2(
        _envelope(
            runtime_id,
            request_id=request_id,
            session_token="A" * 43,
            credentials=[_credential("L" * 43)],
        )
    )

    assert result["error"]["code"] == "LEGACY_LEASE_AUTHORITY_REMOVED"
    assert rpc.dispatch_count == 0
    assert replay.status(runtime_id, request_id).status == "unknown"


@pytest.mark.unit
def test_completed_mutation_replays_across_authenticated_session_refresh(_rpc_runtime):
    runtime_id, _manager, replay = _rpc_runtime
    request_id = _uuid()
    operation_id = _uuid()
    first = _envelope(
        runtime_id,
        request_id=request_id,
        session_token="A" * 43,
    )
    first["operation"]["task_id"] = operation_id
    refreshed = copy.deepcopy(first)
    refreshed["session_token"] = "B" * 43
    rpc = _CountingRPC()

    initial = rpc.invoke_v2(first)
    repeated = rpc.invoke_v2(refreshed)

    assert initial == repeated
    assert rpc.dispatch_count == 1
    assert replay.status(runtime_id, request_id).status == "completed"
    entry = replay._entries[(runtime_id, request_id)]
    assert entry.process_pinned is False


@pytest.mark.unit
def test_generated_operation_is_verified_then_replayed_with_refreshed_signature(
    _rpc_runtime,
):
    runtime_id, _manager, _replay = _rpc_runtime
    request_id = _uuid()
    params = {
        "code": "doc.addObject('Part::Feature', 'Once')",
        "options": {
            "document": "Model",
            "affected_documents": ["Model"],
            "generated_operation": True,
            "operation_id": "partdesign.create-once",
        },
    }
    first = _envelope(
        runtime_id,
        request_id=request_id,
        session_token="A" * 43,
        method="execute_code",
        params=copy.deepcopy(params),
    )
    first["params"]["options"]["operation_signature"] = (
        addon_rpc._generated_execute_signature(
            session_token=first["session_token"],
            request_id=request_id,
            code=first["params"]["code"],
            options=first["params"]["options"],
        )
    )
    refreshed = copy.deepcopy(first)
    refreshed["session_token"] = "B" * 43
    refreshed["params"]["options"]["operation_signature"] = (
        addon_rpc._generated_execute_signature(
            session_token=refreshed["session_token"],
            request_id=request_id,
            code=refreshed["params"]["code"],
            options=refreshed["params"]["options"],
        )
    )
    rpc = _CountingRPC()

    assert rpc.invoke_v2(first)["ok"] is True
    assert rpc.invoke_v2(refreshed)["ok"] is True
    assert rpc.dispatch_count == 1

    invalid = copy.deepcopy(refreshed)
    invalid["params"]["options"]["operation_signature"] = (
        "hmac-sha256:" + "0" * 64
    )
    rejected = rpc.invoke_v2(invalid)
    assert rejected["error"]["code"] == "GENERATED_OPERATION_SIGNATURE_INVALID"
    assert rpc.dispatch_count == 1


@pytest.mark.unit
def test_post_dispatch_exception_is_process_pinned_and_not_reapplied(monkeypatch):
    runtime_id = _uuid()
    request_id = _uuid()
    now = [1.0]
    replay = RequestReplayCache(
        ttl_seconds=1,
        monotonic=lambda: now[0],
    )
    monkeypatch.setattr(addon_rpc, "rpc_session_manager", _SessionManager(runtime_id))
    monkeypatch.setattr(addon_rpc, "rpc_request_replay_cache", replay)
    monkeypatch.setattr(
        addon_rpc, "rpc_inflight_request_registry", InflightRequestRegistry()
    )
    monkeypatch.setattr(addon_rpc, "rpc_server_runtime_id", _uuid())
    request_identity.set_request_identity(instance_id=runtime_id)
    rpc = _CountingRPC(error=RuntimeError("escaped after dispatch"))
    payload = _envelope(
        runtime_id,
        request_id=request_id,
        session_token="A" * 43,
    )
    try:
        first = rpc.invoke_v2(payload)
        now[0] = 10.0
        assert replay.prune() == 0
        second = rpc.invoke_v2(payload)
    finally:
        request_identity.clear_request_identity()

    assert first["error"]["code"] == "REQUEST_OUTCOME_UNCERTAIN"
    assert second["error"]["code"] == "REQUEST_ALREADY_COMPLETED"
    assert rpc.dispatch_count == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "uncertain_result",
    [
        {
            "success": False,
            "error_code": "GUI_TIMEOUT",
            "completion_uncertain": True,
            "error": "GUI completion is unknown",
        },
        {
            "success": False,
            "error_code": "REQUEST_CANCELLED_AFTER_MUTATION",
            "error": "Cancellation arrived after mutation began",
        },
    ],
)
def test_native_uncertain_result_is_process_pinned_and_not_reapplied(
    monkeypatch, uncertain_result
):
    runtime_id = _uuid()
    request_id = _uuid()
    now = [1.0]
    replay = RequestReplayCache(
        ttl_seconds=1,
        monotonic=lambda: now[0],
    )
    monkeypatch.setattr(addon_rpc, "rpc_session_manager", _SessionManager(runtime_id))
    monkeypatch.setattr(addon_rpc, "rpc_request_replay_cache", replay)
    monkeypatch.setattr(
        addon_rpc, "rpc_inflight_request_registry", InflightRequestRegistry()
    )
    monkeypatch.setattr(addon_rpc, "rpc_server_runtime_id", _uuid())
    request_identity.set_request_identity(instance_id=runtime_id)
    rpc = _CountingRPC(uncertain_result)
    payload = _envelope(
        runtime_id,
        request_id=request_id,
        session_token="A" * 43,
    )
    try:
        first = rpc.invoke_v2(payload)
        now[0] = 10.0
        assert replay.prune() == 0
        repeated = rpc.invoke_v2(payload)
    finally:
        request_identity.clear_request_identity()

    assert first["ok"] is False
    assert repeated["error"]["code"] == "REQUEST_ALREADY_COMPLETED"
    assert rpc.dispatch_count == 1


@pytest.mark.unit
def test_authenticated_typed_timeout_replays_late_result_once_and_reports_status(
    _rpc_runtime,
):
    """The real typed RPC and MCP adapters recover one late native callback."""
    runtime_id, _manager, replay = _rpc_runtime
    owner = [None]
    wake = threading.Event()
    core = GuiDispatchCore(
        is_gui_thread=lambda: threading.get_ident() == owner[0],
        wake_gui=wake.set,
        schedule_wake=lambda _delay, callback: callback(),
        gui_busy=lambda: False,
        emit_telemetry=lambda *_args, **_kwargs: None,
    )
    entered = threading.Event()
    release = threading.Event()

    created = []

    def create_leaf(document_name, obj, *, recompute):
        assert document_name == "Model"
        assert recompute is False
        entered.set()
        assert release.wait(5.0), "test did not release the native callback"
        created.append(obj.name)
        return True  # The production public adapter must type this late sentinel.

    class NativeCommit:
        def commit_compatibility_mutation(
            self, document_name, callback, *, structural, recompute=True, postcondition
        ):
            assert document_name == "Model" and structural and recompute
            callback()
            assert postcondition() is True
            return {"status": "Committed", "committed": True}

    native = NativeCommit()
    document = attach_native_readiness(SimpleNamespace(Name="Model"))
    freecad = SimpleNamespace(getDocument=lambda name: document if name == "Model" else None)
    base = addon_rpc.FreeCADRPC()
    rpc = addon_rpc.FreeCADRPC(
        collaboration_collaborators=replace(
            base._collaboration_collaborators, compatibility_api=native, freecad=freecad
        ),
        execution_collaborators=replace(
            base._execution_collaborators,
            compatibility_api=native, freecad=freecad, gui_dispatcher=core,
        ),
        cad_collaborators=replace(
            base._cad_collaborators,
            compatibility_api=native, freecad=freecad, create_object_gui=create_leaf,
            validate_document_invariants=lambda _document: None,
        ),
    )
    rpc.TIMEOUT = 0.2
    request_id = _uuid()
    payload = _envelope(runtime_id, request_id=request_id, session_token="A" * 43)
    result_box = []

    class TypedConnection:
        _identity_lock = threading.Lock()
        _rpc_session = None

        def create_object(self, document_name, data):
            assert document_name == "Model" and data["Name"] == "Once"
            return FreeCADConnection._unwrap_v2_response(self, rpc.invoke_v2(payload))

    connection = TypedConnection()

    def call_tool():
        return create_object_operation(connection, True, "Model", "Part::Feature", "Once")

    def invoke_in_worker():
        request_identity.set_request_identity(instance_id=runtime_id)
        try:
            result_box.append(call_tool())
        finally:
            request_identity.clear_request_identity()

    caller = threading.Thread(target=invoke_in_worker)

    def drain():
        owner[0] = threading.get_ident()
        core.drain_one()

    gui = threading.Thread(target=drain)

    def request_status():
        query = _envelope(
            runtime_id, request_id=_uuid(), session_token="A" * 43,
            method="get_request_status", params={"request_id": request_id},
        )
        return rpc.invoke_v2_control(query)["result"]

    try:
        caller.start()
        assert wake.wait(2.0), result_box
        gui.start()
        assert entered.wait(2.0)
        caller.join(2.0)
        assert not caller.is_alive()
        timed_out = result_box[0]
        assert timed_out.isError
        failure = timed_out.structuredContent["data"]
        assert failure["request_id"] == request_id
        assert failure["error_code"] == "GUI_TIMEOUT_DURING_EXECUTION"
        assert failure["completion_uncertain"] is True
        live_status = request_status()
        assert live_status["state"] == "running_after_timeout"
        assert live_status["completion_uncertain"] is True

        # A repeated tool request reads the timeout; it cannot enqueue a second create.
        assert call_tool().structuredContent["data"]["completion_uncertain"] is True
        assert created == []
        release.set()
        gui.join(2.0)
        assert not gui.is_alive()
        late = replay.status(runtime_id, request_id).response
        assert late and late["late_completion"] is True
        completed_status = request_status()
        assert completed_status["state"] == "completed"
        assert completed_status["late_completion_available"] is True
        recovered = call_tool()
        assert not recovered.isError
        assert recovered.structuredContent["data"]["object_name"] == "Once"
        assert created == ["Once"]
        # Quarantine has ended; the owner may execute fresh GUI work.
        owner[0] = threading.get_ident()
        assert core.submit(lambda: "ready", timeout=0.2) == "ready"
    finally:
        release.set()
        if caller.ident is not None:
            caller.join(2.0)
        if gui.ident is not None:
            gui.join(2.0)


@pytest.mark.unit
def test_process_journal_object_survives_listener_session_manager_replacement(
    _rpc_runtime, monkeypatch
):
    runtime_id, _old_manager, replay = _rpc_runtime
    request_id = _uuid()
    payload = _envelope(
        runtime_id,
        request_id=request_id,
        session_token="A" * 43,
    )
    rpc = _CountingRPC()
    assert rpc.invoke_v2(payload)["ok"] is True

    # Listener restart replaces authenticated sessions but deliberately keeps
    # the addon-process journal object and MCP runtime identity.
    replacement = _SessionManager(runtime_id)
    monkeypatch.setattr(addon_rpc, "rpc_session_manager", replacement)
    restarted_payload = copy.deepcopy(payload)
    restarted_payload["session_token"] = "B" * 43
    assert addon_rpc.rpc_request_replay_cache is replay
    assert rpc.invoke_v2(restarted_payload)["ok"] is True
    assert rpc.dispatch_count == 1
