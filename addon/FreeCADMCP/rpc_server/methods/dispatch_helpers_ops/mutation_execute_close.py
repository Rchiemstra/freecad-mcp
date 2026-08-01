from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *

"""Close-mutation handling for execute_mutation_with_health."""


def finalize_close_mutation(self, transaction, spec, result, failed, *, declared_names, request_id):
    if failed:
        transaction.abort()
    else:
        transaction.commit()
    if not isinstance(result, dict):
        result = {"success": not failed, "result": result}
    result = dict(result)
    evidence = self._unknown_mutation_evidence(
        spec.name,
        declared_documents=declared_names,
        coverage=RollbackCoverage.UNAVAILABLE,
        reason=(
            "target document closed successfully"
            if not failed
            else "close failed before terminal identity validation"
        ),
    )
    result.update(evidence)
    emit_telemetry(
        "document_health",
        "document_health_checked",
        status=result["document_health"]["verdict"],
        request_id=request_id,
        execution_id=request_id,
        payload={
            "operation": spec.name,
            "document_health": result["document_health"],
            "transaction": result["transaction"],
        },
    )
    return result, failed
