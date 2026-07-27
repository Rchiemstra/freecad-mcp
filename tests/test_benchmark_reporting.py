from __future__ import annotations

import json

import pytest

from benchmarks.report import write_reports
from benchmarks.runner import TaskResult, calculate_kpis, evaluate_quality_gates
from benchmarks.tasks import BENCHMARK_TASKS


pytestmark = pytest.mark.unit


def _result(task_id: str, *, category: str, protected: bool = False) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        task_type="policy" if protected else "model",
        success=True,
        first_attempt_success=True,
        outcome="rejected" if protected else "succeeded",
        duration_ms=10,
        tool_calls=1,
        argument_valid=True,
        tool_selection_accurate=True,
        completed_response=True,
        execution_category=category,
        generated_internal_calls=0,
        protected_rejection=protected,
        false_positive_rejection=False,
        unexpected_runtime_failure=False,
        safe_failure=protected,
        recovery_success=True,
        rollback_success=True,
        health_regression=False,
        unrelated_document_mutation=False,
        timeout_stage=None,
        tokens=None,
        evidence={"new_recompute_errors": 0},
        validation_failures=[],
    )


def test_catalog_has_complete_required_metadata():
    assert len(BENCHMARK_TASKS) == 20
    for task in BENCHMARK_TASKS:
        payload = task.to_dict()
        assert set(payload) == {
            "task_id",
            "task_type",
            "attempt_number",
            "expected_tool_or_tool_family",
            "expected_outcome",
            "expected_modified_documents",
            "expected_modified_objects",
            "forbidden_side_effects",
            "time_budget",
            "call_budget",
            "probe",
        }
        assert task.time_budget > 0 and task.call_budget > 0


def test_kpis_keep_protected_rejections_and_categories_separate():
    tasks = [
        _result("one", category="typed_direct_rpc"),
        _result("two", category="public_execute_code"),
        _result("three", category="typed_direct_rpc", protected=True),
    ]
    tasks[0].task_type = "save_reopen_validate"
    kpis = calculate_kpis(tasks)
    assert kpis["task_success_rate"] == 1
    assert kpis["protected_rejection_rate"] == 1
    assert kpis["safe_failure_rate"] == 1
    assert kpis["public_execute_code_share"] == pytest.approx(1 / 3, abs=1e-6)
    assert kpis["typed_tool_share"] == pytest.approx(2 / 3, abs=1e-6)
    assert kpis["unexpected_non_task_timeout_rate"] == 0
    assert evaluate_quality_gates(kpis)["passed"]


def test_optional_token_metric_uses_only_supplied_client_counts():
    measured = _result("measured", category="typed_direct_rpc")
    unmeasured = _result("unmeasured", category="typed_direct_rpc")
    measured.tokens = 240
    kpis = calculate_kpis([measured, unmeasured])
    assert kpis["tokens_per_successful_task"] == 240
    assert kpis["token_metric_coverage_rate"] == 0.5
