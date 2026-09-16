from __future__ import annotations

from ..cad_methods_ops.mutation_readiness import document_readiness, mark_quarantined

# ruff: noqa: F403, F405
from ._support import *

"""Post-mutation health aggregation for execute_mutation_with_health."""


def collect_unexpected_documents(freecad, all_before, declared_names):
    unexpected_documents = []
    all_after_documents = tuple(freecad.listDocuments().values())
    for document in all_after_documents:
        name = str(getattr(document, "Name", "") or "")
        if name in declared_names:
            continue
        previous = all_before.get(name)
        current = capture_document_health(document, profile=ValidationProfile.MINIMAL)
        if previous is None or (
            previous.object_signatures != current.object_signatures
            or previous.object_count != current.object_count
            or previous.document_dirty != current.document_dirty
        ):
            unexpected_documents.append(name)
    for name in set(all_before).difference(
        str(getattr(document, "Name", "") or "") for document in all_after_documents
    ):
        if name not in declared_names:
            unexpected_documents.append(name)
    return unexpected_documents


def build_health_deltas(before, after, affected):
    return [
        calculate_document_health_delta(
            before[name],
            after[name],
            expected_modified_objects=affected,
        )
        for name in before
    ]


def finalize_mutation_health(  # noqa: C901
    self,
    *,
    transaction,
    spec,
    result,
    failed,
    before,
    documents,
    expected,
    declared_names,
    attempted_deltas,
    unexpected_documents,
    validation_error,
    request_id,
):
    final_deltas = attempted_deltas
    if transaction.abort_attempted:
        final_deltas = []
        for document in documents:
            name = str(getattr(document, "Name", "") or "")
            final_snapshot = capture_document_health(
                document,
                profile=spec.validation_profile,
                affected_objects=expected,
            )
            final_deltas.append(
                calculate_document_health_delta(
                    before[name],
                    final_snapshot,
                    expected_modified_objects=expected,
                    validation_error=(
                        "transaction rollback failed"
                        if transaction.abort_succeeded is False
                        else None
                    ),
                )
            )
    health = self._aggregate_document_health(
        final_deltas,
        unexpected_documents=unexpected_documents,
    )
    if attempted_deltas:
        attempted_health = self._aggregate_document_health(
            attempted_deltas,
            unexpected_documents=unexpected_documents,
        )
        health["attempted_verdict"] = attempted_health["verdict"]
        if attempted_health.get("invalid_object_status"):
            health["attempted_invalid_object_status"] = attempted_health[
                "invalid_object_status"
            ]
    health["rollback_restored_health"] = bool(
        transaction.abort_succeeded
        and health["verdict"]
        in {
            DocumentHealthVerdict.HEALTHY.value,
            DocumentHealthVerdict.WARNING.value,
        }
    )
    if validation_error:
        health["validation_error"] = validation_error
    transaction_data = transaction.to_dict(coverage=spec.rollback_coverage)
    if not isinstance(result, dict):
        result = {"success": not failed, "result": result}
    else:
        result = dict(result)
    result["transaction"] = transaction_data
    result["document_health"] = health
    result["mutation_scope"] = {
        "declared_documents": sorted(declared_names),
        "expected_modified_objects": sorted(expected),
        "transaction_coverage": transaction_data["coverage"],
        "rollback_policy": (
            "abort_on_failure_or_degraded_health" if transaction.enabled else "none"
        ),
    }
    if transaction.abort_succeeded is False:
        for document in documents:
            mark_quarantined(document, "transaction rollback failed")
    post_readiness = [document_readiness(document) for document in documents]
    result["mutation_readiness"] = post_readiness
    if transaction.abort_succeeded is False:
        result.update(
            success=False,
            outcome_status="degraded",
            error_code="TRANSACTION_ROLLBACK_FAILED",
            error="Document transaction rollback failed",
        )
    elif (
        health.get("attempted_verdict")
        in {
            DocumentHealthVerdict.DEGRADED.value,
            DocumentHealthVerdict.INVALID.value,
        }
        and not failed
    ):
        result.update(
            success=False,
            outcome_status="degraded",
            error_code="DOCUMENT_HEALTH_DEGRADED",
            error="Mutation was rolled back because document health degraded",
        )
        failed = True
    elif (
        any(
            any(reason != "automation_paused" for reason in item["reasons"])
            for item in post_readiness
        )
        and not failed
    ):
        result["ready_for_next_mutation"] = False
        result["readiness_warning"] = {
            "code": "MUTATION_NOT_READY_AFTER_COMMIT",
            "message": (
                "Mutation committed but the document is not ready for another mutation"
            ),
        }
        result["retryable"] = False
    emit_telemetry(
        "document_health",
        "document_health_checked",
        status=health["verdict"],
        error_code=result.get("error_code"),
        request_id=request_id,
        execution_id=request_id,
        payload={
            "operation": spec.name,
            "document_health": health,
            "transaction": transaction_data,
        },
    )
    return result, bool(
        failed or result.get("success") is False or result.get("ok") is False
    )
