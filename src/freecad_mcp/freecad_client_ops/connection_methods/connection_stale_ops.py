"""FreeCADConnection method implementations."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from ...lease_manager import (
    STALE_RECOVERY_EXEMPT_RPC_METHODS,
    STALE_RECOVERY_RETRY_ERROR_CODE,
    STALE_RECOVERY_TRIGGER_PRE_OPERATION,
    STALE_RECOVERY_TRIGGER_RPC_REFUSAL,
    RpcRequestContext,
    StaleRecoveryResult,
    rpc_response_indicates_stale_refusal,
    summarize_stale_recovery_results,
)

logger = logging.getLogger("FreeCADMCPserver")



def stale_recovery_status(conn) -> dict[str, Any]:
        orchestrator = conn._stale_recovery
        if orchestrator is None:
            return summarize_stale_recovery_results({})
        return orchestrator.recovery_status_snapshot()


def _reconcile_stale_session(conn, document_session_uuid: str) -> dict[str, Any]:
        return conn.reconcile_document_lease(document_session_uuid)


def _maybe_recover_stale_before_protected_rpc(
        conn,
        method: str,
        context: RpcRequestContext,
    ) -> None:
        orchestrator = conn._stale_recovery
        if orchestrator is None or method in STALE_RECOVERY_EXEMPT_RPC_METHODS:
            return
        if not context.lease_credentials:
            return
        session_uuids = tuple(
            item.document_session_uuid for item in context.lease_credentials
        )
        orchestrator.recover_sessions_blocking(
            session_uuids,
            STALE_RECOVERY_TRIGGER_PRE_OPERATION,
            conn._reconcile_stale_session,
        )


def _retryable_stale_recovery_response(
        conn,
        *,
        method: str,
        request_id: str,
        outcomes: Mapping[str, StaleRecoveryResult],
    ) -> dict[str, Any]:
        recovery = summarize_stale_recovery_results(outcomes)
        recovered = recovery["succeeded"]
        return {
            "ok": False,
            "success": False,
            "error": {
                "code": STALE_RECOVERY_RETRY_ERROR_CODE,
                "message": (
                    "Protected operation was refused because the document lease "
                    "was stale; automatic exact-owner recovery recovered the "
                    "lease and the operation was not replayed — retry the same "
                    "protected call"
                    if recovered
                    else (
                        "Protected operation was refused because the document "
                        "lease is stale; automatic exact-owner recovery has not "
                        "completed yet — retry the protected call after recovery "
                        "succeeds"
                    )
                ),
            },
            "error_code": STALE_RECOVERY_RETRY_ERROR_CODE,
            "retryable": True,
            "mutation_replayed": False,
            "stale_recovery_attempted": recovery["attempted"],
            "stale_recovery_succeeded": recovered,
            "stale_recovery_refused": recovery["refused"],
            "stale_recovery_unnecessary": recovery["unnecessary"],
            "stale_recovery": recovery,
            "request_id": request_id,
            "method": method,
        }


def _handle_stale_rpc_refusal(
        conn,
        response: Mapping[str, Any],
        *,
        method: str,
        context: RpcRequestContext,
    ) -> dict[str, Any] | None:
        if method in STALE_RECOVERY_EXEMPT_RPC_METHODS:
            return None
        if not context.lease_credentials:
            return None
        if not rpc_response_indicates_stale_refusal(response):
            return None

        orchestrator = conn._stale_recovery
        session_uuids = tuple(
            item.document_session_uuid for item in context.lease_credentials
        )
        outcomes: dict[str, StaleRecoveryResult] = {}
        if orchestrator is not None:
            for session_uuid in session_uuids:
                orchestrator.mark_needs_recovery(session_uuid)
            outcomes = orchestrator.recover_sessions_blocking(
                session_uuids,
                STALE_RECOVERY_TRIGGER_RPC_REFUSAL,
                conn._reconcile_stale_session,
            )
        return conn._retryable_stale_recovery_response(
            method=method,
            request_id=context.request_id,
            outcomes=outcomes,
        )
