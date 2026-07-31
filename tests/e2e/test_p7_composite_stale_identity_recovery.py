"""P7 composite stale recovery + field-incident boundary tests (S6-A).

Mock end-to-end wiring across lease service, RPC reconcile, observer GUI-save
fencing, and MCP stale-recovery orchestration. No live FreeCAD process required.
"""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from unittest import mock

import pytest

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
from addon.FreeCADMCP.document_lease.observer import LeaseObserver
from addon.FreeCADMCP.rpc_server import rpc_server as addon_rpc
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.lease_manager import (
    STALE_RECOVERY_OUTCOME_RECOVERED,
    STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL,
    STALE_RECOVERY_TRIGGER_HEARTBEAT,
    LeaseClientManager,
    LeaseCredential,
    RpcRequestContext,
    StaleLeaseRecoveryOrchestrator,
    reconcile_refusal_is_terminal,
)


class _Document:
    def __init__(self, name: str, path: str = "", *, modified: bool = False) -> None:
        self.Name = name
        self.Label = name
        self.FileName = path
        self.Modified = modified


class _TrackedGuiDispatch:
    def __init__(self, events: list[str] | None = None, *, after_first=None) -> None:
        self.events = events if events is not None else []
        self.after_first = after_first
        self.calls = 0

    def __call__(self, task, timeout=None):
        del timeout
        self.calls += 1
        call_number = self.calls
        result: list[object] = []
        failure: list[BaseException] = []

        def run() -> None:
            self.events.append(f"gui-enter-{call_number}")
            try:
                result.append(task())
            except BaseException as exc:
                failure.append(exc)
            finally:
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
        client="p7-composite",
        agent_id="agent-a",
    )


def _atomic_replace_same_content(model, replacement, *, content: bytes) -> None:
    replacement.write_bytes(content)
    if model.exists():
        model.unlink()
    replacement.replace(model)


def _wire_from_grant(grant) -> dict[str, object]:
    return {
        "lease_id": grant.credential.lease_id,
        "document_session_uuid": grant.credential.document_session_uuid,
        "generation": grant.credential.generation,
        "token": grant.credential.token,
    }


def _control_reconcile_invoke_rpc(
    rpc,
    owner: LeaseOwner,
    *,
    reconcile_results: list[dict] | None = None,
    mutation_response: dict | None = None,
):
    """Route MCP control-lane lease_reconcile through invoke_v2 -> invoke_rpc."""

    def invoke_rpc(transport_method, envelope, *, control=False, timeout=None):
        del timeout
        if transport_method == "invoke_v2_control":
            method = envelope.get("method")
            if method == "lease_reconcile":
                set_request_identity(
                    instance_id=owner.mcp_instance_id,
                    authenticated_session_id=str(uuid.uuid4()),
                    request_id=str(uuid.uuid4()),
                )
                credential = envelope.get("params", {}).get("credential", {})
                result = rpc.lease_reconcile(credential)
                if reconcile_results is not None:
                    reconcile_results.append(result)
                return {"ok": True, "result": result}
        if transport_method == "invoke_v2" and mutation_response is not None:
            return mutation_response
        return {
            "ok": False,
            "error": {
                "code": "UNEXPECTED_RPC",
                "message": str(transport_method),
            },
        }

    return invoke_rpc


def _install_rpc_runtime(
    monkeypatch,
    *,
    document,
    identities: DocumentIdentityService,
    service: DocumentLeaseService,
    owner: LeaseOwner,
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


def _install_stale_dirty_saved(
    tmp_path,
    monkeypatch,
    *,
    content: bytes = b"composite-baseline-payload",
):
    model = tmp_path / "composite-stale.FCStd"
    model.write_bytes(content)
    document = _Document("CompositeStale", str(model), modified=True)
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
    service.begin_mutation(grant.credential, operation="long-probe")
    service.complete_operation(grant.credential, dirty=True)
    stale = service.mark_stale(identity.session_uuid)
    assert stale.state == LeaseState.STALE
    wire = _wire_from_grant(grant)
    return {
        "model": model,
        "content": content,
        "document": document,
        "identities": identities,
        "service": service,
        "grant": grant,
        "wire": wire,
        "owner": owner,
        "session_uuid": identity.session_uuid,
    }


@pytest.fixture(autouse=True)
def _clean_request_identity():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


@pytest.mark.unit
def test_composite_identity_drift_and_stale_recovers_without_agent_repair(
    tmp_path, monkeypatch
):
    ctx = _install_stale_dirty_saved(tmp_path, monkeypatch)
    replacement = tmp_path / "replacement.FCStd"
    _atomic_replace_same_content(
        ctx["model"],
        replacement,
        content=ctx["content"],
    )
    rpc, dispatch = _install_rpc_runtime(
        monkeypatch,
        document=ctx["document"],
        identities=ctx["identities"],
        service=ctx["service"],
        owner=ctx["owner"],
    )

    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(
        LeaseCredential(
            lease_id=ctx["wire"]["lease_id"],
            document_session_uuid=ctx["session_uuid"],
            generation=int(ctx["wire"]["generation"]),
            token=str(ctx["wire"]["token"]),
        )
    )
    connection = FreeCADConnection(host="127.0.0.1", port=1)
    connection.configure_lease_routing(manager, lambda _name: ctx["session_uuid"])
    orchestrator = StaleLeaseRecoveryOrchestrator()
    connection.configure_stale_recovery(orchestrator)

    reconcile_results: list[dict] = []

    with mock.patch.object(
        connection,
        "invoke_rpc",
        side_effect=_control_reconcile_invoke_rpc(
            rpc,
            ctx["owner"],
            reconcile_results=reconcile_results,
        ),
    ):
        stale_sessions = orchestrator.observe_heartbeat_batch(
            {
                "leases": [
                    {
                        "document_session_uuid": ctx["session_uuid"],
                        "error_code": "LEASE_STATE_FORBIDS_OPERATION",
                        "details": {"state": "STALE"},
                    }
                ]
            }
        )

        async def run_recovery() -> dict:
            return await orchestrator.recover_sessions(
                stale_sessions,
                STALE_RECOVERY_TRIGGER_HEARTBEAT,
                connection._reconcile_stale_session,
            )

        results = asyncio.run(run_recovery())

    assert reconcile_results, "reconcile was not invoked"
    assert reconcile_results[0].get("success"), reconcile_results[0]
    assert results[ctx["session_uuid"]].outcome == STALE_RECOVERY_OUTCOME_RECOVERED
    assert ctx["service"].get(ctx["session_uuid"])["lease"]["state"] == (
        LeaseState.LOCKED_IDLE.value
    )
    assert len(ctx["service"].list_identity_refresh_events()) == 1
    assert dispatch.calls == 2

    # Typed lease save path must authorize after automatic recovery.
    saving = ctx["service"].begin_save(ctx["grant"].credential)
    assert saving.state == LeaseState.LOCKED_SAVING


@pytest.mark.unit
def test_field_incident_ctrl_s_after_stale_is_user_intervention_not_reclaimed(
    tmp_path, monkeypatch
):
    ctx = _install_stale_dirty_saved(tmp_path, monkeypatch)
    replacement = tmp_path / "user-save.FCStd"
    observer = LeaseObserver(service_provider=lambda: ctx["service"])
    rpc, _dispatch = _install_rpc_runtime(
        monkeypatch,
        document=ctx["document"],
        identities=ctx["identities"],
        service=ctx["service"],
        owner=ctx["owner"],
    )

    # Field incident: user presses Ctrl+S on a still-dirty document while STALE.
    replacement.write_bytes(b"user protected geometry on disk")
    ctx["model"].unlink()
    replacement.replace(ctx["model"])
    assert ctx["document"].Modified is True

    started = observer.slotStartSaveDocument(ctx["document"], ctx["document"].FileName)
    assert started is not None
    assert started.state == LeaseState.USER_INTERVENED

    finished = observer.slotFinishSaveDocument(
        ctx["document"], ctx["document"].FileName
    )

    assert finished.state == LeaseState.USER_INTERVENED
    public = ctx["service"].get(ctx["session_uuid"])
    assert public["lease"]["state"] == LeaseState.USER_INTERVENED.value

    reconcile_result = rpc.lease_reconcile(ctx["wire"])
    assert reconcile_result["success"] is False
    assert reconcile_result["error_code"] == "LEASE_AUTHORIZATION_FAILED"
    assert ctx["service"].get(ctx["session_uuid"])["lease"]["state"] == (
        LeaseState.USER_INTERVENED.value
    )

    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(
        LeaseCredential(
            lease_id=ctx["wire"]["lease_id"],
            document_session_uuid=ctx["session_uuid"],
            generation=int(ctx["wire"]["generation"]),
            token=str(ctx["wire"]["token"]),
        )
    )
    orchestrator = StaleLeaseRecoveryOrchestrator()
    orchestrator.mark_needs_recovery(ctx["session_uuid"])

    def reconcile(session_uuid: str) -> dict:
        set_request_identity(
            instance_id=ctx["owner"].mcp_instance_id,
            authenticated_session_id=str(uuid.uuid4()),
            request_id=str(uuid.uuid4()),
        )
        return rpc.lease_reconcile(ctx["wire"])

    async def run_recovery() -> dict:
        return await orchestrator.recover_sessions(
            (ctx["session_uuid"],),
            STALE_RECOVERY_TRIGGER_HEARTBEAT,
            reconcile,
        )

    results = asyncio.run(run_recovery())
    assert results[ctx["session_uuid"]].outcome == (
        STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL
    )
    assert reconcile_refusal_is_terminal(reconcile_result) is True
    assert ctx["service"].get(ctx["session_uuid"])["lease"]["state"] == (
        LeaseState.USER_INTERVENED.value
    )


@pytest.mark.unit
def test_composite_recovery_refuses_changed_disk_baseline(tmp_path, monkeypatch):
    ctx = _install_stale_dirty_saved(tmp_path, monkeypatch)
    before = ctx["model"].stat()
    original = ctx["model"].read_bytes()

    def tamper_after_expectation_capture() -> None:
        changed = bytes(byte ^ 0xFF for byte in original)
        ctx["model"].write_bytes(changed)
        os.utime(ctx["model"], ns=(before.st_atime_ns, before.st_mtime_ns))

    dispatch = _TrackedGuiDispatch([], after_first=tamper_after_expectation_capture)
    rpc, _ = _install_rpc_runtime(
        monkeypatch,
        document=ctx["document"],
        identities=ctx["identities"],
        service=ctx["service"],
        owner=ctx["owner"],
    )
    rpc._dispatch_gui = dispatch

    result = rpc.lease_reconcile(ctx["wire"])

    assert result["success"] is False
    assert result["error_code"] == "LIVE_DOCUMENT_VALIDATION_FAILED"
    assert "does not exactly match" in result["error"]
    assert ctx["service"].get(ctx["session_uuid"])["lease"]["state"] == (
        LeaseState.STALE.value
    )


@pytest.mark.unit
def test_composite_recovery_refuses_competing_sidecar_authority(
    tmp_path, monkeypatch
):
    ctx = _install_stale_dirty_saved(tmp_path, monkeypatch)
    stale_record = ctx["service"]._records[ctx["session_uuid"]]  # noqa: SLF001

    def replace_sidecar_after_expectation_capture() -> None:
        path = sidecar_path_for(ctx["model"])
        changed = stale_record.revised(current_operation="concurrent recovery")
        ctx["service"].sidecar_store.replace(path, changed, expected=stale_record)

    dispatch = _TrackedGuiDispatch([], after_first=replace_sidecar_after_expectation_capture)
    rpc, _ = _install_rpc_runtime(
        monkeypatch,
        document=ctx["document"],
        identities=ctx["identities"],
        service=ctx["service"],
        owner=ctx["owner"],
    )
    rpc._dispatch_gui = dispatch

    result = rpc.lease_reconcile(ctx["wire"])

    assert result["success"] is False
    assert result["error_code"] in {
        "LIVE_DOCUMENT_VALIDATION_FAILED",
        "LEASE_COORDINATION_LOST",
    }
    assert ctx["service"].get(ctx["session_uuid"])["lease"]["state"] == (
        LeaseState.STALE.value
    )


@pytest.mark.unit
def test_mcp_pre_operation_does_not_reclaim_after_field_incident_ctrl_s(
    tmp_path, monkeypatch
):
    ctx = _install_stale_dirty_saved(tmp_path, monkeypatch)
    observer = LeaseObserver(service_provider=lambda: ctx["service"])
    rpc, _ = _install_rpc_runtime(
        monkeypatch,
        document=ctx["document"],
        identities=ctx["identities"],
        service=ctx["service"],
        owner=ctx["owner"],
    )

    orchestrator = StaleLeaseRecoveryOrchestrator()
    loop = asyncio.new_event_loop()
    orchestrator.bind_event_loop(loop)
    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(
        LeaseCredential(
            lease_id=ctx["wire"]["lease_id"],
            document_session_uuid=ctx["session_uuid"],
            generation=int(ctx["wire"]["generation"]),
            token=str(ctx["wire"]["token"]),
        )
    )
    connection = FreeCADConnection(host="127.0.0.1", port=1)
    connection.configure_lease_routing(manager, lambda _name: ctx["session_uuid"])
    connection.configure_stale_recovery(orchestrator)

    orchestrator.observe_heartbeat_batch(
        {
            "leases": [
                {
                    "document_session_uuid": ctx["session_uuid"],
                    "error_code": "LEASE_STATE_FORBIDS_OPERATION",
                    "details": {"state": "STALE"},
                }
            ]
        }
    )

    replacement = tmp_path / "field-incident.FCStd"
    replacement.write_bytes(b"field incident changed bytes")
    ctx["model"].unlink()
    replacement.replace(ctx["model"])
    assert ctx["document"].Modified is True
    observer.slotStartSaveDocument(ctx["document"], ctx["document"].FileName)
    observer.slotFinishSaveDocument(ctx["document"], ctx["document"].FileName)
    assert ctx["service"].get(ctx["session_uuid"])["lease"]["state"] == (
        LeaseState.USER_INTERVENED.value
    )

    reconcile_results: list[dict] = []

    with mock.patch.object(
        connection,
        "invoke_rpc",
        side_effect=_control_reconcile_invoke_rpc(
            rpc,
            ctx["owner"],
            reconcile_results=reconcile_results,
            mutation_response={
                "ok": False,
                "error": {
                    "code": "LEASE_STATE_FORBIDS_OPERATION",
                    "message": "USER_INTERVENED",
                },
                "details": {"state": "USER_INTERVENED"},
            },
        ),
    ):
        context = RpcRequestContext(
            request_id=str(uuid.uuid4()),
            session_token="rpc-session",
            lease_credentials=(
                LeaseCredential(
                    lease_id=ctx["wire"]["lease_id"],
                    document_session_uuid=ctx["session_uuid"],
                    generation=int(ctx["wire"]["generation"]),
                    token=str(ctx["wire"]["token"]),
                ),
            ),
            operation_name="Protected edit after field incident",
        )
        connection.invoke_v2(
            "edit_object",
            {"document": "CompositeStale"},
            context,
        )

    assert reconcile_results, "pre-operation recovery must attempt reconcile"
    assert reconcile_results[0].get("success") is False
    assert reconcile_refusal_is_terminal(reconcile_results[0]) is True
    assert ctx["service"].get(ctx["session_uuid"])["lease"]["state"] == (
        LeaseState.USER_INTERVENED.value
    )
    recovery = orchestrator.last_recovery_results().get(ctx["session_uuid"])
    assert recovery is not None
    assert recovery.outcome == STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL
    loop.close()
