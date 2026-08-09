"""Stale recovery status and RPC response helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .heartbeat_helpers import heartbeat_item_lease_state
from .stale_recovery_constants import (
    _TERMINAL_RECONCILE_ERROR_CODES,
    STALE_RECOVERY_OUTCOME_RECOVERED,
    STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE,
    STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL,
    STALE_RECOVERY_OUTCOME_SKIPPED_BACKOFF,
    STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL,
    STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY,
    _upper_state,
)
from .stale_recovery_result import StaleRecoveryResult


def reconcile_refusal_is_terminal(response: Mapping[str, Any]) -> bool:
    """True when a lease_reconcile refusal should stop automatic recovery."""

    if not isinstance(response, Mapping):
        return False
    error_code = _upper_state(
        response.get("error_code") or response.get("code")
    )
    if error_code in _TERMINAL_RECONCILE_ERROR_CODES:
        return True
    if error_code == "LEASE_STATE_FORBIDS_OPERATION":
        state = heartbeat_item_lease_state(response)
        return state == "USER_INTERVENED"
    return False


def reconcile_response_is_idempotent(response: Mapping[str, Any]) -> bool:
    """True when lease_reconcile succeeded without a STALE->LOCKED transition."""

    if not isinstance(response, Mapping) or not response.get("success"):
        return False
    if response.get("idempotent") is True:
        return True
    return response.get("already_active") is True


def rpc_response_indicates_stale_refusal(response: Mapping[str, Any]) -> bool:
    """True when an RPC envelope proves the lease blocked the call as STALE."""

    candidates: list[Mapping[str, Any]] = [response]
    result = response.get("result")
    if isinstance(result, Mapping):
        candidates.append(result)
    error = response.get("error")
    if isinstance(error, Mapping):
        candidates.append(error)

    for candidate in candidates:
        error_code = _upper_state(
            candidate.get("error_code") or candidate.get("code")
        )
        if error_code == "LEASE_STALE":
            return True
        if error_code == "LEASE_STATE_FORBIDS_OPERATION":
            state = heartbeat_item_lease_state(candidate)
            if state == "STALE":
                return True
            details = candidate.get("details")
            if isinstance(details, Mapping) and _upper_state(details.get("state")) == "STALE":
                return True
    return False

def rpc_response_mutation_may_have_begun(response: Mapping[str, Any]) -> bool:
    """Return whether the RPC layer recorded that a mutation may have started."""

    candidates: list[Mapping[str, Any]] = [response]
    result = response.get("result")
    if isinstance(result, Mapping):
        candidates.append(result)
    for candidate in candidates:
        if bool(candidate.get("mutation_may_have_begun")):
            return True
        details = candidate.get("details")
        if isinstance(details, Mapping) and bool(
            details.get("mutation_may_have_begun")
        ):
            return True
    return False

def stale_recovery_result_to_dict(result: StaleRecoveryResult) -> dict[str, Any]:
    """Return a stable, token-free stale-recovery status record."""

    attempted = result.outcome not in {
        STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY,
        STALE_RECOVERY_OUTCOME_SKIPPED_BACKOFF,
        STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL,
    }
    return {
        "document_session_uuid": result.document_session_uuid,
        "trigger": result.trigger,
        "outcome": result.outcome,
        "reason_code": result.reason_code,
        "attempted": attempted,
        "succeeded": result.outcome == STALE_RECOVERY_OUTCOME_RECOVERED,
        "refused": result.outcome
        in {
            STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE,
            STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL,
        },
        "unnecessary": result.outcome == STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY,
    }

def summarize_stale_recovery_results(
    results: Mapping[str, StaleRecoveryResult],
) -> dict[str, Any]:
    """Summarize one batch of per-document stale-recovery outcomes."""

    sessions = [
        stale_recovery_result_to_dict(item)
        for _, item in sorted(results.items())
    ]
    if not sessions:
        return {
            "sessions": [],
            "attempted": False,
            "succeeded": False,
            "refused": False,
            "unnecessary": False,
        }
    return {
        "sessions": sessions,
        "attempted": any(item["attempted"] for item in sessions),
        "succeeded": any(item["succeeded"] for item in sessions),
        "refused": any(item["refused"] for item in sessions),
        "unnecessary": all(item["unnecessary"] for item in sessions),
    }
