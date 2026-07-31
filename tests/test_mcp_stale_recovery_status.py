"""P6 stale-recovery status surfacing."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest import mock

import pytest

from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.lease_manager import (
    STALE_RECOVERY_OUTCOME_RECOVERED,
    STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE,
    STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY,
    STALE_RECOVERY_RETRY_ERROR_CODE,
    STALE_RECOVERY_TRIGGER_RPC_REFUSAL,
    LeaseClientManager,
    LeaseCredential,
    RpcRequestContext,
    StaleLeaseRecoveryOrchestrator,
    StaleRecoveryResult,
    stale_recovery_result_to_dict,
    summarize_stale_recovery_results,
)


def _credential(session: str, token: str) -> LeaseCredential:
    return LeaseCredential(
        lease_id=f"lease-{session}",
        document_session_uuid=session,
        generation=1,
        token=token,
    )


def _request_context(session: str, token: str) -> RpcRequestContext:
    return RpcRequestContext(
        request_id=str(uuid.uuid4()),
        session_token="rpc-session",
        lease_credentials=(_credential(session, token),),
        operation_name="Protected edit",
    )


@pytest.mark.unit
def test_stale_recovery_result_to_dict_flags():
    recovered = stale_recovery_result_to_dict(
        StaleRecoveryResult(
            document_session_uuid="doc-a",
            trigger="heartbeat_stale_observed",
            outcome=STALE_RECOVERY_OUTCOME_RECOVERED,
        )
    )
    assert recovered["attempted"] is True
    assert recovered["succeeded"] is True
    assert recovered["refused"] is False
    assert recovered["unnecessary"] is False

    unnecessary = stale_recovery_result_to_dict(
        StaleRecoveryResult(
            document_session_uuid="doc-a",
            trigger="pre_operation_lazy",
            outcome=STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY,
        )
    )
    assert unnecessary["attempted"] is False
    assert unnecessary["unnecessary"] is True


@pytest.mark.unit
def test_orchestrator_records_last_recovery_results():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    orchestrator.mark_needs_recovery("doc-a")

    results = orchestrator.recover_sessions_blocking(
        ("doc-a",),
        STALE_RECOVERY_TRIGGER_RPC_REFUSAL,
        lambda _session: {
            "success": False,
            "error_code": "LEASE_STALE",
        },
    )

    assert results["doc-a"].outcome == STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE
    snapshot = orchestrator.recovery_status_snapshot()
    assert snapshot["attempted"] is True
    assert snapshot["refused"] is True
    assert snapshot["sessions"][0]["reason_code"] == "LEASE_STALE"
    assert "token" not in snapshot


@pytest.mark.unit
def test_rpc_stale_refusal_response_includes_structured_recovery():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    loop = __import__("asyncio").new_event_loop()
    orchestrator.bind_event_loop(loop)
    connection = FreeCADConnection(host="127.0.0.1", port=1)
    connection.configure_lease_routing(
        LeaseClientManager(session_token="rpc-session"),
        lambda _name: "doc-a",
    )
    connection.configure_stale_recovery(orchestrator)

    def fake_invoke_rpc(*_args, **_kwargs):
        return {
            "ok": False,
            "error_code": "LEASE_STATE_FORBIDS_OPERATION",
            "details": {"state": "STALE"},
        }

    with mock.patch.object(connection, "invoke_rpc", side_effect=fake_invoke_rpc), mock.patch.object(
        connection,
        "reconcile_document_lease",
        return_value={"success": True},
    ):
        response = connection.invoke_v2(
            "edit_object",
            {"document": "Doc"},
            _request_context("doc-a", "secret-a"),
        )

    assert response["error_code"] == STALE_RECOVERY_RETRY_ERROR_CODE
    assert response["stale_recovery"]["succeeded"] is True
    assert response["stale_recovery"]["sessions"][0]["outcome"] == (
        STALE_RECOVERY_OUTCOME_RECOVERED
    )
    assert "restart" not in response["error"]["message"].lower()
    assert "sidecar" not in response["error"]["message"].lower()
    assert "secret-a" not in str(response)
    loop.close()


@pytest.mark.unit
def test_summarize_stale_recovery_results_empty():
    summary = summarize_stale_recovery_results({})
    assert summary["sessions"] == []
    assert summary["attempted"] is False
    assert summary["succeeded"] is False
    assert summary["refused"] is False
    assert summary["unnecessary"] is False


@pytest.mark.unit
def test_unbound_stale_recovery_status_is_honest_empty():
    connection = FreeCADConnection(host="127.0.0.1", port=1)
    summary = connection.stale_recovery_status()
    assert summary["sessions"] == []
    assert summary["unnecessary"] is False


@pytest.mark.unit
def test_empty_recover_sessions_blocking_does_not_claim_unnecessary():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    outcomes = orchestrator.recover_sessions_blocking(
        ("doc-a",),
        STALE_RECOVERY_TRIGGER_RPC_REFUSAL,
        lambda _session: {"success": True},
    )
    assert outcomes == {}
    summary = summarize_stale_recovery_results(outcomes)
    assert summary["unnecessary"] is False


@pytest.mark.unit
def test_stale_refusal_without_orchestrator_does_not_claim_unnecessary():
    connection = FreeCADConnection(host="127.0.0.1", port=1)

    def fake_invoke_rpc(*_args, **_kwargs):
        return {
            "ok": False,
            "error_code": "LEASE_STATE_FORBIDS_OPERATION",
            "details": {"state": "STALE"},
        }

    with mock.patch.object(connection, "invoke_rpc", side_effect=fake_invoke_rpc):
        response = connection.invoke_v2(
            "edit_object",
            {"document": "Doc"},
            _request_context("doc-a", "secret-a"),
        )

    assert response["stale_recovery_unnecessary"] is False
    assert response["stale_recovery"]["unnecessary"] is False
    assert response["stale_recovery"]["sessions"] == []
    assert "secret-a" not in str(response.get("stale_recovery", {}))
