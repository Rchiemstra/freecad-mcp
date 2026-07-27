"""Common benchmark evidence checks."""

from __future__ import annotations

from typing import Any, Mapping

from benchmarks.tasks.catalog import BenchmarkTask


def validate_observation(
    task: BenchmarkTask, observation: Mapping[str, Any]
) -> list[str]:
    failures: list[str] = []
    if observation.get("outcome") != task.expected_outcome:
        failures.append(
            f"outcome={observation.get('outcome')!r}, "
            f"expected={task.expected_outcome!r}"
        )
    calls = int(observation.get("tool_calls") or 0)
    if calls > task.call_budget:
        failures.append(f"call budget exceeded: {calls}>{task.call_budget}")
    if float(observation.get("duration_ms") or 0.0) > task.time_budget * 1000:
        failures.append("time budget exceeded")
    modified_documents = set(observation.get("modified_documents") or ())
    expected_documents = set(task.expected_modified_documents)
    if not modified_documents.issubset(expected_documents):
        failures.append(
            "unexpected modified documents: "
            + ", ".join(sorted(modified_documents - expected_documents))
        )
    modified_objects = set(observation.get("modified_objects") or ())
    missing = set(task.expected_modified_objects).difference(modified_objects)
    if missing:
        failures.append("missing expected objects: " + ", ".join(sorted(missing)))
    if observation.get("unrelated_document_mutation"):
        failures.append("unrelated document mutation")
    if observation.get("unclassified_failure"):
        failures.append("unclassified failure")
    return failures


__all__ = ["validate_observation"]
