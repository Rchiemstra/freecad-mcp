"""Machine-readable and Markdown benchmark report generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from benchmarks.runner import BenchmarkRun


def load_baseline(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("benchmark baseline must contain a JSON object")
    return value


def _baseline_flags(
    current: Mapping[str, Any], baseline: Mapping[str, Any] | None
) -> list[str]:
    if not baseline:
        return []
    previous = baseline.get("kpis", baseline)
    flags: list[str] = []
    for key in (
        "task_success_rate",
        "first_attempt_success_rate",
        "tool_execution_success_rate",
        "safe_failure_rate",
        "typed_tool_share",
    ):
        old = previous.get(key)
        new = current.get(key)
        if isinstance(old, (int, float)) and isinstance(new, (int, float)):
            if new + 0.01 < old:
                flags.append(f"{key} regressed from {old:.3f} to {new:.3f}")
    return flags


def write_reports(run: BenchmarkRun, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "benchmark-results.json"
    markdown_path = output_dir / "benchmark-report.md"
    payload = run.to_dict()
    flags = _baseline_flags(run.kpis, run.baseline)
    payload["regression_flags"] = flags
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# FreeCAD MCP Benchmark Report",
        "",
        f"- Tasks passed: {sum(item.success for item in run.tasks)}/{len(run.tasks)}",
        f"- Quality gates: {'PASS' if run.quality_gates['passed'] else 'FAIL'}",
        f"- Regression flags: {len(flags)}",
        "",
        "## KPIs",
        "",
        "| KPI | Value |",
        "|---|---:|",
    ]
    for key, value in sorted(run.kpis.items()):
        if isinstance(value, dict):
            rendered = "`" + json.dumps(value, sort_keys=True) + "`"
        else:
            rendered = str(value)
        lines.append(f"| {key} | {rendered} |")
    lines.extend(
        [
            "",
            "## Task results",
            "",
            "| Task | Type | Outcome | Passed | Duration (ms) | Calls |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    for item in run.tasks:
        lines.append(
            f"| {item.task_id} | {item.task_type} | {item.outcome} | "
            f"{'yes' if item.success else 'no'} | {item.duration_ms:.3f} | "
            f"{item.tool_calls} |"
        )
    lines.extend(["", "## Regression flags", ""])
    lines.extend(f"- {item}" for item in flags)
    if not flags:
        lines.append("- None (or no baseline supplied).")
    lines.extend(["", "## Baseline comparison", ""])
    if run.baseline:
        previous = run.baseline.get("kpis", run.baseline)
        lines.extend(
            [
                "| KPI | Baseline | Current |",
                "|---|---:|---:|",
            ]
        )
        for key in sorted(set(previous).intersection(run.kpis)):
            old = previous.get(key)
            new = run.kpis.get(key)
            if isinstance(old, (int, float)) and isinstance(new, (int, float)):
                lines.append(f"| {key} | {old} | {new} |")
    else:
        lines.append(
            "- No prior benchmark JSON was supplied; this run establishes the baseline."
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


__all__ = ["load_baseline", "write_reports"]
