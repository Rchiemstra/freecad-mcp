"""LOCKED_ERROR handoff continuation phase helpers."""

from .handoff_continuation_authorize import (
    authorize_handoff_gui as authorize_handoff_gui_phase,
)
from .handoff_continuation_authorize import (
    hash_handoff_baseline,
)
from .handoff_continuation_claim import (
    claim_handoff_gui as claim_handoff_gui_phase,
)
from .handoff_continuation_claim import (
    claim_late_complete,
)
from .handoff_escrow import escrow_locked_error_handoff_claim
from .handoff_journal import journal_handoff_terminal


def journal_cancelled_handoff(self, store, mcp_runtime_id, request_id):
    if store is None or store.get(mcp_runtime_id, request_id) is None:
        return
    entry = store.get(mcp_runtime_id, request_id)
    if entry is None or entry.state != "cancelled":
        return
    journal_handoff_terminal(
        self,
        mcp_runtime_id=mcp_runtime_id,
        request_id=request_id,
        response={
            "ok": False,
            "request_id": request_id,
            "addon_runtime_id": self._collaboration_collaborators.rpc_server_runtime_id,
            "result": {
                "success": False,
                "error_code": "LOCKED_ERROR_HANDOFF_CANCELLED",
                "error": entry.error or "LOCKED_ERROR handoff was cancelled",
                "request_id": request_id,
                "confirmation_pending": False,
                "handoff_pending": False,
            },
        },
    )


def publish_handoff_failure(self, store, mcp_runtime_id, request_id, code, message):
    if store is not None:
        store.update(
            mcp_runtime_id,
            request_id,
            state=(
                "denied"
                if code.endswith("NOT_CONFIRMED")
                or "not authorized" in str(message).lower()
                else "failed"
            ),
            stage="handoff_failed",
            error_code=code,
            error=str(message),
        )
    journal_handoff_terminal(
        self,
        mcp_runtime_id=mcp_runtime_id,
        request_id=request_id,
        response={
            "ok": False,
            "request_id": request_id,
            "addon_runtime_id": self._collaboration_collaborators.rpc_server_runtime_id,
            "result": {
                "success": False,
                "error_code": code,
                "error": str(message),
                "request_id": request_id,
                "confirmation_pending": False,
                "handoff_pending": False,
            },
        },
    )


def run_handoff_authorize_phase(
    self,
    *,
    store,
    cancelled,
    fail,
    mcp_runtime_id,
    request_id,
    requested_selector,
    phase,
    acquire_timeout,
):
    if cancelled():
        fail(
            "LOCKED_ERROR_HANDOFF_CANCELLED",
            "LOCKED_ERROR handoff was cancelled before authorization",
        )
        return False
    if store is not None:
        store.update(
            mcp_runtime_id,
            request_id,
            state="authorizing",
            stage="handoff_authorize",
        )

    def authorize_handoff_gui():
        return authorize_handoff_gui_phase(
            self,
            cancelled=cancelled,
            requested_selector=requested_selector,
            request_id=request_id,
            phase=phase,
        )

    authorized = self._dispatch_gui(authorize_handoff_gui, timeout=acquire_timeout)
    if cancelled():
        fail(
            "LOCKED_ERROR_HANDOFF_CANCELLED",
            "LOCKED_ERROR handoff was cancelled after authorization",
        )
        return False
    if not isinstance(authorized, dict) or not authorized.get("success"):
        code = (
            (authorized or {}).get("error_code")
            if isinstance(authorized, dict)
            else "DIRTY_ADOPTION_PRECONDITION_FAILED"
        )
        message = (
            (authorized or {}).get("error")
            if isinstance(authorized, dict)
            else "LOCKED_ERROR handoff authorization failed"
        )
        fail(
            str(code or "DIRTY_ADOPTION_PRECONDITION_FAILED"),
            message or "LOCKED_ERROR handoff authorization failed",
        )
        return False
    return True


def run_handoff_hash_phase(
    self, store, cancelled, fail, mcp_runtime_id, request_id, phase, lease
):
    if cancelled():
        fail(
            "LOCKED_ERROR_HANDOFF_CANCELLED",
            "LOCKED_ERROR handoff was cancelled before hashing",
        )
        return False
    if store is not None:
        store.update(
            mcp_runtime_id,
            request_id,
            state="hashing",
            stage="acquisition_hash",
        )
    return hash_handoff_baseline(self, phase, lease, fail)


def run_handoff_claim_phase(
    self,
    *,
    store,
    cancelled,
    fail,
    mcp_runtime_id,
    request_id,
    phase,
    task_description,
    lease,
    acquire_timeout,
):
    if cancelled():
        fail(
            "LOCKED_ERROR_HANDOFF_CANCELLED",
            "LOCKED_ERROR handoff was cancelled before claim",
        )
        return None
    if store is not None:
        store.update(
            mcp_runtime_id,
            request_id,
            state="claiming",
            stage="acquisition_claim",
        )

    def claim_handoff_gui():
        return claim_handoff_gui_phase(
            self,
            store=store,
            mcp_runtime_id=mcp_runtime_id,
            request_id=request_id,
            phase=phase,
            task_description=task_description,
            lease=lease,
        )

    return self._dispatch_gui(
        claim_handoff_gui,
        timeout=acquire_timeout,
        late_on_complete=lambda _completed_request_id, outcome: claim_late_complete(
            self,
            outcome,
            store=store,
            mcp_runtime_id=mcp_runtime_id,
            request_id=request_id,
            fail=fail,
        ),
    )


def finalize_handoff_claim(self, claimed, store, mcp_runtime_id, request_id, fail):
    if isinstance(claimed, dict) and claimed.get("completion_uncertain"):
        if store is not None:
            entry = store.get(mcp_runtime_id, request_id)
            if entry is not None and entry.state != "claimable":
                store.update(
                    mcp_runtime_id,
                    request_id,
                    state="claiming_uncertain",
                    stage="acquisition_claim",
                )
        return
    if (
        self._collaboration_collaborators.acquisition_claim_store is not None
        and self._collaboration_collaborators.acquisition_claim_store.claimable(
            mcp_runtime_id, request_id
        )
    ):
        return
    if not isinstance(claimed, dict) or not claimed.get("success"):
        code = (
            (claimed or {}).get("error_code")
            if isinstance(claimed, dict)
            else "LEASE_CONFLICT"
        )
        message = (
            (claimed or {}).get("error")
            if isinstance(claimed, dict)
            else "LOCKED_ERROR handoff claim failed"
        )
        fail(str(code or "LEASE_CONFLICT"), message)
        return
    escrow_locked_error_handoff_claim(
        self,
        mcp_runtime_id=mcp_runtime_id,
        request_id=request_id,
        claimed=claimed,
    )
