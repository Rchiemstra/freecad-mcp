"""The required 20 end-to-end task definitions and immutable expectations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class BenchmarkTask:
    task_id: str
    task_type: str
    attempt_number: int
    expected_tool_or_tool_family: str
    expected_outcome: str
    expected_modified_documents: tuple[str, ...]
    expected_modified_objects: tuple[str, ...]
    forbidden_side_effects: tuple[str, ...]
    time_budget: float
    call_budget: int
    probe: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "expected_modified_documents",
            "expected_modified_objects",
            "forbidden_side_effects",
        ):
            value[key] = list(value[key])
        return value


def _task(
    number: int,
    task_type: str,
    family: str,
    probe: str,
    *,
    outcome: str = "succeeded",
    documents: tuple[str, ...] = ("target",),
    objects: tuple[str, ...] = (),
    calls: int = 4,
    seconds: float = 15.0,
) -> BenchmarkTask:
    return BenchmarkTask(
        task_id=f"G3-{number:02d}",
        task_type=task_type,
        attempt_number=1,
        expected_tool_or_tool_family=family,
        expected_outcome=outcome,
        expected_modified_documents=documents,
        expected_modified_objects=objects,
        forbidden_side_effects=("unrelated_document_mutation", "credential_exposure"),
        time_budget=seconds,
        call_budget=calls,
        probe=probe,
    )


BENCHMARK_TASKS = (
    _task(1, "create_document", "document_lifecycle", "create_document", objects=()),
    _task(2, "acquire_lease", "document_lease", "lease_lifecycle", documents=()),
    _task(3, "rectangle_pad", "partdesign", "partdesign_pad", objects=("Body", "Sketch", "Pad"), calls=8),
    _task(4, "attach_pocket", "partdesign", "part_cut", objects=("Pad", "Pocket"), calls=7),
    _task(5, "spreadsheet_expressions", "parametric", "spreadsheet", objects=("Dimensions", "Driven"), calls=6),
    _task(6, "datum_binder", "partdesign_reference", "datum_binder", objects=("Datum", "Binder"), calls=5),
    _task(7, "assembly_joint", "assembly", "assembly_joint", objects=("Assembly", "Joint"), calls=5),
    _task(8, "worker_geometry_analysis", "worker_analysis", "geometry_analysis", documents=(), calls=2),
    _task(9, "unsafe_gui_loop_rejection", "policy", "policy_loop", outcome="rejected", documents=(), calls=1),
    _task(10, "invalid_link_input", "validation", "invalid_link", outcome="rejected", documents=(), calls=1),
    _task(11, "broken_reference_repair", "references", "reference_repair", objects=("Source", "Consumer"), calls=5),
    _task(12, "typed_mutation_rollback", "transaction", "transaction_rollback", objects=("RollbackProbe",), calls=2),
    _task(13, "worker_timeout_cancel", "worker_lifecycle", "worker_timeout", outcome="cancelled", documents=(), calls=3),
    _task(14, "gui_timeout_late_completion", "gui_lifecycle", "gui_timeout", outcome="timed_out", documents=(), calls=2),
    _task(15, "recovery_synchronization", "recovery", "recovery", documents=(), calls=2),
    _task(16, "save_reopen_validate", "save", "save_reopen", objects=("SavedShape",), calls=5, seconds=30.0),
    _task(17, "snapshot_corrupt_restore", "snapshot", "snapshot_restore", objects=("Restored",), calls=5),
    _task(18, "multi_document_scope", "policy", "scope_protection", outcome="rejected", documents=(), calls=2),
    _task(19, "public_execute_gap", "public_execute_code", "public_execute", documents=(), calls=1),
    _task(20, "typed_equivalent", "typed_direct_rpc", "typed_equivalent", objects=("TypedResult",), calls=2),
)


__all__ = ["BENCHMARK_TASKS", "BenchmarkTask"]
