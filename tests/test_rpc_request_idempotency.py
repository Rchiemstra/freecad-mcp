"""Lease-lifetime request-id guarantees at the authenticated RPC boundary."""

from __future__ import annotations

import copy
import uuid
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP import document_lock
from addon.FreeCADMCP.rpc_server.inflight_requests import InflightRequestRegistry
from addon.FreeCADMCP.rpc_server.lease_protocol import (
    RequestEnvelope,
    RequestReplayCache,
)
from addon.FreeCADMCP.rpc_server.mutation_guard import make_method_spec
from addon.FreeCADMCP.rpc_server import rpc_server as addon_rpc


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
    replay = RequestReplayCache(owner_has_unresolved_lease=lambda _owner: True)
    registry = InflightRequestRegistry()
    monkeypatch.setattr(addon_rpc, "rpc_session_manager", manager)
    monkeypatch.setattr(addon_rpc, "rpc_request_replay_cache", replay)
    monkeypatch.setattr(addon_rpc, "rpc_inflight_request_registry", registry)
    monkeypatch.setattr(addon_rpc, "rpc_server_runtime_id", _uuid())
    monkeypatch.setattr(addon_rpc, "document_lease_service", None)
    document_lock.set_request_identity(instance_id=runtime_id)
    try:
        yield runtime_id, manager, replay
    finally:
        document_lock.clear_request_identity()


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
        "lease_credentials": credentials
        if credentials is not None
        else [_credential("L" * 43)],
        "operation": {"name": "Idempotency test", "task_id": _uuid()},
    }


@pytest.mark.unit
def test_method_descriptor_pin_policy_excludes_reads_and_automatic_heartbeat():
    assert make_method_spec("create_object", "MUTATING").pin_replay_for_lease_lifetime
    assert make_method_spec(
        "acquire_document_lock", "LIFECYCLE"
    ).pin_replay_for_lease_lifetime
    assert make_method_spec(
        "lease_reconcile", "LIFECYCLE"
    ).pin_replay_for_lease_lifetime
    assert make_method_spec(
        "update_document_lock", "LIFECYCLE"
    ).pin_replay_for_lease_lifetime
    assert not make_method_spec(
        "lease_heartbeat_batch", "LIFECYCLE"
    ).pin_replay_for_lease_lifetime
    assert not make_method_spec("get_objects", "READ_ONLY").pin_replay_for_lease_lifetime


@pytest.mark.unit
def test_completed_mutation_replays_across_authenticated_session_refresh(_rpc_runtime):
    runtime_id, _manager, replay = _rpc_runtime
    request_id = _uuid()
    operation_id = _uuid()
    credential = _credential("L" * 43)
    first = _envelope(
        runtime_id,
        request_id=request_id,
        session_token="A" * 43,
        credentials=[credential],
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


@pytest.mark.unit
def test_generated_operation_is_verified_then_replayed_with_refreshed_signature(
    _rpc_runtime,
):
    runtime_id, _manager, _replay = _rpc_runtime
    request_id = _uuid()
    credential = _credential("G" * 43)
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
        credentials=[credential],
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
def test_acquisition_token_is_returned_once_and_never_retained(_rpc_runtime):
    runtime_id, _manager, replay = _rpc_runtime
    request_id = _uuid()
    raw_token = "one-time-acquisition-token-that-must-not-be-cached"
    payload = _envelope(
        runtime_id,
        request_id=request_id,
        session_token="A" * 43,
        method="acquire_document_lock",
        params={
            "selector": {"document_name": "Model"},
            "task_description": "one time",
        },
        credentials=[],
    )
    rpc = _CountingRPC(
        {
            "success": True,
            "credential": {
                "lease_id": _uuid(),
                "document_session_uuid": _uuid(),
                "generation": 1,
                "token": raw_token,
            },
        }
    )

    initial = rpc.invoke_v2(payload)
    repeated = rpc.invoke_v2(payload)

    assert initial["result"]["credential"]["token"] == raw_token
    assert repeated["error"]["code"] == "ACQUISITION_RESULT_NOT_REPLAYABLE"
    assert rpc.dispatch_count == 1
    assert raw_token not in repr(replay._entries)


@pytest.mark.unit
def test_post_dispatch_exception_is_process_pinned_and_never_reapplied(monkeypatch):
    runtime_id = _uuid()
    request_id = _uuid()
    now = [1.0]
    replay = RequestReplayCache(
        ttl_seconds=1,
        monotonic=lambda: now[0],
        owner_has_unresolved_lease=lambda _owner: False,
    )
    monkeypatch.setattr(addon_rpc, "rpc_session_manager", _SessionManager(runtime_id))
    monkeypatch.setattr(addon_rpc, "rpc_request_replay_cache", replay)
    monkeypatch.setattr(
        addon_rpc, "rpc_inflight_request_registry", InflightRequestRegistry()
    )
    monkeypatch.setattr(addon_rpc, "rpc_server_runtime_id", _uuid())
    monkeypatch.setattr(addon_rpc, "document_lease_service", None)
    document_lock.set_request_identity(instance_id=runtime_id)
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
        document_lock.clear_request_identity()

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
def test_normal_uncertain_result_is_process_pinned_without_owner(
    monkeypatch, uncertain_result
):
    runtime_id = _uuid()
    request_id = _uuid()
    now = [1.0]
    replay = RequestReplayCache(
        ttl_seconds=1,
        monotonic=lambda: now[0],
        owner_has_unresolved_lease=lambda _owner: False,
    )
    monkeypatch.setattr(addon_rpc, "rpc_session_manager", _SessionManager(runtime_id))
    monkeypatch.setattr(addon_rpc, "rpc_request_replay_cache", replay)
    monkeypatch.setattr(
        addon_rpc, "rpc_inflight_request_registry", InflightRequestRegistry()
    )
    monkeypatch.setattr(addon_rpc, "rpc_server_runtime_id", _uuid())
    monkeypatch.setattr(addon_rpc, "document_lease_service", None)
    document_lock.set_request_identity(instance_id=runtime_id)
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
        document_lock.clear_request_identity()

    assert first["ok"] is False
    assert repeated["error"]["code"] == "REQUEST_ALREADY_COMPLETED"
    assert rpc.dispatch_count == 1


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
