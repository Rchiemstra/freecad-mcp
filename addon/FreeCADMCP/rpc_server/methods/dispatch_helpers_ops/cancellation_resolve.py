from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *

"""Helpers for ``complete_request_cancellation``."""

ACQUISITION_CANCEL_METHODS = frozenset(
    {
        "acquire_document_lock",
        "adopt_dirty_document",
        "create_document",
    }
)


def cancellation_wait_timeout():
    return 0.0 if _rpc_mod().shutdown_requested.is_set() else None


def resolve_cached_or_wait(self, inflight, *, claimed, cached, wait_timeout):
    if claimed:
        return None
    if cached is not None:
        _rpc_mod().rpc_inflight_request_registry.refresh_terminal(
            inflight.session_id, inflight.request_id
        )
        return cached
    return self._wait_for_cancellation_resolution(inflight, wait_timeout=wait_timeout)


def cancel_acquisition_credentials(self, inflight, snapshot, *, snapshot_id):
    results = []
    may_have_mutated = bool(snapshot.mutation_started or snapshot.uncertain)
    if _rpc_mod().document_lease_service is None:
        return results
    for private in inflight.affected_credentials:
        credential = self._model_credential(private)
        try:
            if may_have_mutated:
                record = _rpc_mod().document_lease_service.fail_acquisition_after_mutation(
                    credential,
                    message="Acquisition was cancelled after mutation began",
                    request_id=inflight.request_id,
                    dirty=True,
                    snapshot_id=snapshot_id,
                )
                results.append(record.to_public_dict())
            else:
                results.append(
                    _rpc_mod().document_lease_service.abort_acquisition(credential)
                )
        except Exception as exc:
            results.append(
                {
                    "success": False,
                    "error_code": _rpc_mod()._redact_rpc_diagnostic(
                        getattr(exc, "code", type(exc).__name__.upper()),
                        inflight=inflight,
                    ),
                    "error": _rpc_mod()._redact_rpc_diagnostic(exc, inflight=inflight),
                }
            )
    return results


def cancel_lease_credentials(self, inflight, snapshot, *, dirty):
    may_have_mutated = bool(snapshot.mutation_started or snapshot.uncertain)
    results = []
    for private in inflight.affected_credentials:
        credential = self._model_credential(private)
        try:
            _rpc_mod().document_lease_service.begin_cancellation(
                credential,
                request_id=inflight.request_id,
                operation="Cancelling authenticated request",
                mutation_may_have_begun=may_have_mutated,
            )
            completed = _rpc_mod().document_lease_service.complete_cancellation(
                credential,
                request_id=inflight.request_id,
                mutation_may_have_begun=may_have_mutated,
                dirty=dirty,
            )
            results.append(completed.to_public_dict())
        except Exception as exc:
            results.append(
                {
                    "success": False,
                    "error_code": _rpc_mod()._redact_rpc_diagnostic(
                        getattr(exc, "code", type(exc).__name__.upper()),
                        inflight=inflight,
                    ),
                    "error": _rpc_mod()._redact_rpc_diagnostic(exc, inflight=inflight),
                }
            )
    return results
