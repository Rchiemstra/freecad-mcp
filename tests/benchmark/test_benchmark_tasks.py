from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
pytestmark = pytest.mark.benchmark

from benchmarks.report import load_baseline, write_reports  # noqa: E402
from benchmarks.runner import run_catalog  # noqa: E402
from benchmarks.tasks import BENCHMARK_TASKS  # noqa: E402


def test_required_twenty_task_catalog_and_quality_gates(tmp_path):
    assert len(BENCHMARK_TASKS) == 20
    assert [task.task_id for task in BENCHMARK_TASKS] == [
        f"G3-{index:02d}" for index in range(1, 21)
    ]
    run = run_catalog(
        workspace=tmp_path,
        baseline=load_baseline(os.environ.get("FREECAD_MCP_BENCHMARK_BASELINE")),
    )
    output_dir = Path(
        os.environ.get("FREECAD_MCP_BENCHMARK_OUTPUT_DIR") or tmp_path
    )
    json_path, markdown_path = write_reports(run, output_dir)

    assert json_path.name == "benchmark-results.json"
    assert markdown_path.name == "benchmark-report.md"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(payload["tasks"]) == 20
    assert run.quality_gates["passed"], {
        item.task_id: item.validation_failures
        for item in run.tasks
        if not item.success
    }
    assert run.kpis["public_execute_code_share"] < 0.50
    assert run.kpis["unrelated_document_mutation_rate"] == 0
    assert run.kpis["committed_new_recompute_errors"] == 0
