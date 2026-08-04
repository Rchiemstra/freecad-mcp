from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *
from .cancellation_resolve import (
    ACQUISITION_CANCEL_METHODS,
    cancel_acquisition_credentials,
    cancel_lease_credentials,
    cancellation_wait_timeout,
    resolve_cached_or_wait,
)

"""Request cancellation resolution helpers."""


def finish_cancellation_resolution(self, inflight, result):
    """Publish one authoritative result and retire terminal credentials."""
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
        recovery_incident_id=snapshot.recovery_incident_id,
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
    """Resolve typed lease cancellation after the request's actual phase ends."""

    if inflight is None:
        return []
    snapshot = inflight.token.snapshot()
    if not snapshot.cancellation_requested:
        return []
    collaborators = self._execution_collaborators
    wait_timeout = cancellation_wait_timeout(collaborators)
    if inflight.method in ACQUISITION_CANCEL_METHODS:
        claimed, cached = inflight.token.claim_cancellation_resolution()
        resolved = resolve_cached_or_wait(
            self, inflight, claimed=claimed, cached=cached, wait_timeout=wait_timeout
        )
        if resolved is not None:
            return resolved
        results = cancel_acquisition_credentials(
            self, inflight, snapshot, snapshot_id=snapshot_id
        )
        return self._finish_cancellation_resolution(inflight, results)

    begin_result = self._begin_request_cancellation(inflight, wait_timeout=wait_timeout)
    if begin_result is None:
        raise RuntimeError(
            "Cancellation fencing remains owned by another request phase"
        )
    if not inflight.lease_affecting or collaborators.document_lease_service is None:
        claimed, cached = inflight.token.claim_cancellation_resolution()
        resolved = resolve_cached_or_wait(
            self, inflight, claimed=claimed, cached=cached, wait_timeout=wait_timeout
        )
        if resolved is not None:
            return resolved
        return self._finish_cancellation_resolution(inflight, [])

    claimed, cached = inflight.token.claim_cancellation_resolution()
    resolved = resolve_cached_or_wait(
        self, inflight, claimed=claimed, cached=cached, wait_timeout=wait_timeout
    )
    if resolved is not None:
        return resolved
    results = []
    try:
        results = cancel_lease_credentials(self, inflight, snapshot, dirty=dirty)
        return self._finish_cancellation_resolution(inflight, results)
    except Exception:
        self._finish_cancellation_resolution(inflight, results)
        raise


def begin_request_cancellation(self, inflight, *, wait_timeout=None):
    """Commit the single CANCELLING event before queue removal/completion."""

    if inflight is None or not inflight.token.snapshot().cancellation_requested:
        return []
    if inflight.method in ACQUISITION_CANCEL_METHODS:
        return []
    if not inflight.token.claim_cancellation_begin():
        if not inflight.token.wait_cancellation_begin(wait_timeout):
            return None
        return []
    results = []
    try:
        collaborators = self._execution_collaborators
        if not inflight.lease_affecting or collaborators.document_lease_service is None:
            return results
        snapshot = inflight.token.snapshot()
        for private in inflight.affected_credentials:
            try:
                record = collaborators.document_lease_service.begin_cancellation(
                    self._model_credential(private),
                    request_id=inflight.request_id,
                    operation="Cancelling authenticated request",
                    mutation_may_have_begun=(
                        snapshot.mutation_started or snapshot.uncertain
                    ),
                )
                results.append(record.to_public_dict())
            except Exception as exc:
                results.append(
                    {
                        "success": False,
                        "error_code": collaborators.redact_rpc_diagnostic(
                            getattr(exc, "code", type(exc).__name__.upper()),
                            inflight=inflight,
                        ),
                        "error": collaborators.redact_rpc_diagnostic(exc, inflight=inflight),
                    }
                )
        return results
    finally:
        inflight.token.finish_cancellation_begin()
