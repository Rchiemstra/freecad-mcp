"""LOCKED_ERROR handoff continuation orchestration."""

from ._common import logger
from .handoff_continuation_helpers import (
    finalize_handoff_claim,
    journal_cancelled_handoff,
    publish_handoff_failure,
    run_handoff_authorize_phase,
    run_handoff_claim_phase,
    run_handoff_hash_phase,
)


def run_locked_error_handoff_continuation(
    self,
    *,
    request_id,
    mcp_runtime_id,
    requested_selector,
    task_description,
    phase,
):
    """Confirm on GUI (unbounded), then hash/CAS-claim within phase budgets."""

    collaborators = self._collaboration_collaborators
    store = collaborators.handoff_continuation_store
    acquire_timeout = self.ACQUIRE_GUI_PHASE_TIMEOUT_S
    lease = collaborators.import_document_lease()

    def cancelled():
        return store is not None and store.is_cancelled(mcp_runtime_id, request_id)

    def fail(code, message):
        if cancelled():
            journal_cancelled_handoff(self, store, mcp_runtime_id, request_id)
            return
        publish_handoff_failure(self, store, mcp_runtime_id, request_id, code, message)

    try:
        if not run_handoff_authorize_phase(
            self,
            store=store,
            cancelled=cancelled,
            fail=fail,
            mcp_runtime_id=mcp_runtime_id,
            request_id=request_id,
            requested_selector=requested_selector,
            phase=phase,
            acquire_timeout=acquire_timeout,
        ):
            return
        if not run_handoff_hash_phase(
            self, store, cancelled, fail, mcp_runtime_id, request_id, phase, lease
        ):
            return
        claimed = run_handoff_claim_phase(
            self,
            store=store,
            cancelled=cancelled,
            fail=fail,
            mcp_runtime_id=mcp_runtime_id,
            request_id=request_id,
            phase=phase,
            task_description=task_description,
            lease=lease,
            acquire_timeout=acquire_timeout,
        )
        finalize_handoff_claim(
            self, claimed, store, mcp_runtime_id, request_id, fail
        )
    except Exception as exc:
        logger.exception(
            "LOCKED_ERROR handoff continuation failed for %s", request_id
        )
        if (
            collaborators.acquisition_claim_store is not None
            and collaborators.acquisition_claim_store.claimable(
                mcp_runtime_id, request_id
            )
        ):
            return
        fail(
            getattr(exc, "code", type(exc).__name__.upper()),
            collaborators.redact_rpc_diagnostic(exc),
        )
