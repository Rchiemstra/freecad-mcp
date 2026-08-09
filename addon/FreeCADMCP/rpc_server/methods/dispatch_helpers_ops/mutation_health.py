from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *

"""Document health aggregation for GUI mutations."""

def expected_object_names(value):
    """Extract bounded typed object-name hints without inspecting code."""

    names = set()
    ignored = {
        "canonical_path",
        "doc_name",
        "document",
        "document_name",
        "document_session_uuid",
        "file_path",
        "path",
    }

    def visit(item, key="", depth=0):
        if depth > 8 or len(names) >= 128:
            return
        normalized = str(key).lower()
        if isinstance(item, dict):
            for child_key, child in item.items():
                visit(child, str(child_key), depth + 1)
            return
        if isinstance(item, (list, tuple)):
            for child in item[:128]:
                visit(child, key, depth + 1)
            return
        if (
            isinstance(item, str)
            and item
            and normalized not in ignored
            and (
                normalized.endswith("_name")
                or normalized
                in {
                    "object",
                    "objects",
                    "object_name",
                    "object_names",
                    "feature",
                    "features",
                    "created",
                    "deleted",
                    "modified",
                }
            )
        ):
            names.add(item)

    visit(value)
    return tuple(sorted(names))


def aggregate_document_health(deltas, *, unexpected_documents=()):
    rank = {
        DocumentHealthVerdict.UNKNOWN.value: 0,
        DocumentHealthVerdict.HEALTHY.value: 1,
        DocumentHealthVerdict.WARNING.value: 2,
        DocumentHealthVerdict.DEGRADED.value: 3,
        DocumentHealthVerdict.INVALID.value: 4,
    }
    verdict = DocumentHealthVerdict.UNKNOWN.value
    for delta in deltas:
        candidate = delta.verdict.value
        if rank[candidate] > rank[verdict]:
            verdict = candidate
    if (
        unexpected_documents
        and rank[verdict] < rank[DocumentHealthVerdict.DEGRADED.value]
    ):
        verdict = DocumentHealthVerdict.DEGRADED.value
    documents = [item.to_dict() for item in deltas]
    aggregate = {
        "verdict": verdict,
        "documents": documents,
        "unexpected_modified_documents": sorted(
            str(item) for item in unexpected_documents
        ),
    }
    fields = (
        "new_recompute_errors",
        "resolved_recompute_errors",
        "new_invalid_state_objects",
        "new_null_shapes",
        "new_invalid_shapes",
        "created_objects",
        "deleted_objects",
        "modified_objects",
        "unexpected_modified_objects",
    )
    for field_name in fields:
        aggregate[field_name] = sorted(
            {
                f"{item.document_name}.{name}"
                for item in deltas
                for name in getattr(item, field_name)
            }
        )
    invalid_object_status: dict[str, str] = {}
    for item in deltas:
        for object_name, status in (item.invalid_object_status or {}).items():
            key = f"{item.document_name}.{object_name}"
            invalid_object_status[key] = str(status)
    if invalid_object_status:
        aggregate["invalid_object_status"] = dict(sorted(invalid_object_status.items()))
    return aggregate


def unknown_mutation_evidence(
    operation,
    *,
    declared_documents=(),
    coverage=RollbackCoverage.UNAVAILABLE,
    reason="validation unavailable",
):
    coverage_value = str(getattr(coverage, "value", coverage))
    return {
        "document_health": {
            "verdict": DocumentHealthVerdict.UNKNOWN.value,
            "documents": [],
            "validation_available": False,
            "validation_error": str(reason)[:2048],
            "new_recompute_errors": [],
            "new_invalid_shapes": [],
        },
        "transaction": {
            "status": "unavailable",
            "enabled": False,
            "documents": sorted(str(item) for item in declared_documents),
            "started": False,
            "committed": False,
            "abort_attempted": False,
            "abort_succeeded": None,
            "abort_errors": [],
            "rollback_attempted": False,
            "rollback_succeeded": None,
            "coverage": coverage_value,
        },
        "mutation_scope": {
            "declared_documents": sorted(str(item) for item in declared_documents),
            "expected_modified_objects": [],
            "transaction_coverage": coverage_value,
            "rollback_policy": "none",
            "operation": str(operation),
        },
    }


def observed_document_evidence(
    self,
    operation,
    document,
    *,
    profile=ValidationProfile.DEFAULT,
    coverage=RollbackCoverage.PARTIAL,
):
    snapshot = capture_document_health(document, profile=profile)
    delta = calculate_document_health_delta(snapshot, snapshot)
    health = self._aggregate_document_health([delta])
    health["snapshot"] = snapshot.to_dict()
    evidence = self._unknown_mutation_evidence(
        operation,
        declared_documents=(snapshot.document_name,),
        coverage=coverage,
    )
    evidence["document_health"] = health
    return evidence


def adapt_gui_mutation_result(
    result,
    *,
    success_fields=None,
    result_field=None,
    expected_result_type=None,
):
    """Preserve postflight evidence while adapting legacy GUI sentinels.

    Mutation guarding returns a dictionary even when the historical GUI
    helper returned ``True`` or a list. Public RPC methods still expose
    their legacy success fields, augmented with the authoritative health,
    transaction, and mutation-scope records.
    """

    success_fields = dict(success_fields or {})
    if isinstance(result, dict):
        adapted = dict(result)
        failed = adapted.get("success") is False or adapted.get("ok") is False
        if failed:
            return adapted
        value = adapted.get("result")
        if result_field is not None and (
            expected_result_type is None or isinstance(value, expected_result_type)
        ):
            adapted[result_field] = value
        adapted.update(success_fields)
        adapted.setdefault("success", True)
        return adapted
    if result is True:
        return {"success": True, **success_fields}
    if result_field is not None and (
        expected_result_type is None or isinstance(result, expected_result_type)
    ):
        return {
            "success": True,
            result_field: result,
            **success_fields,
        }
    return {"success": False, "error": result}
