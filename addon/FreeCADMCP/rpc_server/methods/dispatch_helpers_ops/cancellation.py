"""Authentication-only request cancellation resolution helpers."""

from __future__ import annotations

from ...telemetry import emit as emit_telemetry


def finish_cancellation_resolution(self, inflight, result):
    """Publish one terminal cancellation result."""

    resolved = (
        self._execution_collaborators.inflight_request_registry
        .finish_cancellation_resolution(inflight, result)
    )
    snapshot = inflight.token.snapshot()
    emit_telemetry(
        "cancellation",
        "cancellation_completed",
        status="cancelled",
        error_code=(
            "REQUEST_CANCELLED_AFTER_MUTATION"
            if snapshot.mutation_started or snapshot.uncertain
            else "REQUEST_CANCELLED"
        ),
        request_id=inflight.request_id,
        execution_id=inflight.request_id,
        payload={
            "mutation_started": snapshot.mutation_started,
            "completion_uncertain": snapshot.uncertain,
        },
    )
    return resolved


def wait_for_cancellation_resolution(self, inflight, *, wait_timeout=None):
    """Wait for the resolver owner; never publish a speculative result."""

    if not inflight.token.wait_cancellation_resolution(wait_timeout):
        raise RuntimeError(
            "Cancellation resolution remains owned by another request phase"
        )
    resolved = inflight.token.cancellation_resolution()
    self._execution_collaborators.inflight_request_registry.refresh_terminal(
        inflight.session_id, inflight.request_id
    )
    return resolved or []


def complete_request_cancellation(self, inflight, *, dirty=None, snapshot_id=None):
    """Resolve cancellation without document credentials or recovery policy."""

    del dirty, snapshot_id
    if inflight is None or not inflight.token.snapshot().cancellation_requested:
        return []
    begin_result = self._begin_request_cancellation(inflight)
    if begin_result is None:
        raise RuntimeError(
            "Cancellation fencing remains owned by another request phase"
        )
    claimed, cached = inflight.token.claim_cancellation_resolution()
    if not claimed:
        if cached is not None:
            return cached
        return self._wait_for_cancellation_resolution(inflight)
    return self._finish_cancellation_resolution(inflight, [])


def begin_request_cancellation(self, inflight, *, wait_timeout=None):
    """Close the generic cancellation gate before queue removal/completion."""

    if inflight is None or not inflight.token.snapshot().cancellation_requested:
        return []
    if not inflight.token.claim_cancellation_begin():
        if not inflight.token.wait_cancellation_begin(wait_timeout):
            return None
        return []
    inflight.token.finish_cancellation_begin()
    return []
