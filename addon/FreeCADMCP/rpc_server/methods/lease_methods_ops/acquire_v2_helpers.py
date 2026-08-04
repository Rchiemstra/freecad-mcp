"""Orchestration helpers for ``acquire_document_lock_v2``."""
from typing import Any

try: from ....dispatch.request_cancellation_error import RequestCancellationError  # noqa: E701, I001 - frozen census lines
except ImportError: from dispatch.request_cancellation_error import RequestCancellationError  # noqa: E701, I001 - frozen census lines
from .acquire_v2_abort import abort_phase_reservation
from .acquire_v2_hash import hash_acquisition_baseline, rollback_after_hash_failure


def validate_acquire_inputs(hash_policy, collaborators) -> dict[str, Any] | None:
    if hash_policy != "sha256":
        return {
            "success": False,
            "error_code": "INVALID_HASH_POLICY",
            "error": "Only the sha256 acquisition baseline is supported",
        }
    if collaborators.runtime_manifest is None:
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_UNAVAILABLE",
            "error": "Authenticated runtime manifest is unavailable",
        }
    return None


def handle_reserve_failure(self, reserved, phase, inflight):
    collaborators = self._collaboration_collaborators
    if isinstance(reserved, dict) and reserved.get("completion_uncertain"):
        if inflight is not None:
            collaborators.inflight_request_registry.request_cancel(
                inflight.session_id, inflight.request_id
            )
        abort_phase_reservation(phase, collaborators)
        if inflight is not None:
            self._complete_request_cancellation(inflight)
    return reserved


def locked_error_handoff_pending_response(request_id):
    return {
        "success": False,
        "error_code": "LOCKED_ERROR_HANDOFF_PENDING",
        "error": (
            "Automatically taking over another agent's dirty LOCKED_ERROR lease"
        ),
        "request_id": request_id,
        "confirmation_pending": False,
        "handoff_pending": True,
    }


def run_hash_phase(self, phase, inflight, request_id, acquire_timeout):
    try:
        self._request_checkpoint("acquisition_hash")
        hash_acquisition_baseline(self, phase)
        self._request_checkpoint("acquisition_hash_complete")
        return None
    except RequestCancellationError:
        self._complete_request_cancellation(inflight)
        raise
    except Exception as exc:
        return rollback_after_hash_failure(
            self, phase, exc, request_id, acquire_timeout
        )


def handle_snapshot_timeout(self, promoted, phase, inflight):
    collaborators = self._collaboration_collaborators
    if not (
        isinstance(promoted, dict)
        and not promoted.get("success")
        and promoted.get("completion_uncertain")
    ):
        return promoted
    if inflight is not None:
        cancellation = collaborators.inflight_request_registry.request_cancel(
            inflight.session_id, inflight.request_id
        )
        if cancellation.status in {"requested", "already_requested"}:
            self._complete_request_cancellation(
                inflight,
                dirty=True,
                snapshot_id=phase.get("snapshot_id"),
            )
    elif phase.get("credential") is not None:
        abort_phase_reservation(phase, collaborators)
    return promoted
