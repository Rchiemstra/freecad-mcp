from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *
from .mutation_execute_finalize import (
    build_health_deltas,
    collect_unexpected_documents,
)


def run_mutation_transaction_body(
    self,
    *,
    documents,
    spec,
    before,
    all_before,
    declared_names,
    expected,
    inflight,
    recompute_callback,
    result,
    failed,
    transaction,
    freecad,
):
    if not failed and spec.recompute:
        if inflight is not None:
            inflight.token.checkpoint("gui_recompute")
        if recompute_callback is not None:
            recompute_callback()
        for document in documents:
            document.recompute()

    get_document = getattr(freecad, "getDocument", lambda _name: None)
    post_documents = tuple(
        get_document(str(getattr(document, "Name", "") or "")) or document
        for document in documents
    )
    if not failed and spec.validator is not None:
        validations = [dict(spec.validator(document)) for document in post_documents]
        if isinstance(result, dict):
            result = dict(result)
            result["postflight_validation"] = validations

    result_names = self._expected_object_names(result)
    affected = expected.union(result_names)
    after = {
        str(getattr(document, "Name", "") or ""): capture_document_health(
            document,
            profile=spec.validation_profile,
            affected_objects=affected,
        )
        for document in post_documents
    }
    attempted_deltas = build_health_deltas(before, after, affected)
    unexpected_documents = collect_unexpected_documents(
        freecad, all_before, declared_names
    )
    attempted_health = self._aggregate_document_health(
        attempted_deltas,
        unexpected_documents=unexpected_documents,
    )
    health_degraded = attempted_health["verdict"] in {
        DocumentHealthVerdict.DEGRADED.value,
        DocumentHealthVerdict.INVALID.value,
    }
    if failed or health_degraded:
        transaction.abort()
    else:
        transaction.commit()
    return result, failed, attempted_deltas, unexpected_documents, None


def mutation_failure_result(result, exc):
    validation_error = f"{type(exc).__name__}: {exc}"[:2048]
    if isinstance(result, dict):
        result = {
            **result,
            "success": False,
            "error_code": getattr(exc, "code", type(exc).__name__.upper()),
            "error": str(exc),
        }
    else:
        result = {
            "success": False,
            "error_code": getattr(exc, "code", type(exc).__name__.upper()),
            "error": str(exc),
        }
    return result, True, validation_error
