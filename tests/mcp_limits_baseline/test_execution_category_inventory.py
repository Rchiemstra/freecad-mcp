#!/usr/bin/env python3
"""Baseline execution-category inventory for run-20260916-mcp-limits (AT-1, AT-5)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parent / "fixtures"
JSONL_PATH = FIXTURES / "mcp_debug_2026-09-16_317891_0a5ddd947d58.jsonl"
INVENTORY_PATH = FIXTURES / "execution_category_inventory.json"

CAMPAIGN_RUN_ID = "run-20260916-mcp-limits"
CANDIDATE_HEAD = "891861f562a78ff97af58c856b67c291449b9075"

WORKER_READ_ONLY_TOOLS = frozenset(
    {
        "spreadsheet_list_aliases",
        "get_sketch_diagnostics",
        "find_faces",
        "find_edges",
        "get_document_tree",
        "inspect_geometry",
        "list_expressions",
        "validate_geometry",
        "audit_hardcoded_dimensions",
        "export_step",
        "bounding_box",
        "measure_volume",
        "capture_state",
    }
)
AUTO_MUTATOR_TOOLS = frozenset(
    {
        "sketch_add_rectangle",
        "sketch_add_circle",
        "sketch_add_slot",
        "sketch_add_polyline",
        "linear_pattern_feature",
        "translate",
        "fillet_feature",
        "import_step",
    }
)
EXPECTED_GENERATED_TOOLS = WORKER_READ_ONLY_TOOLS | AUTO_MUTATOR_TOOLS

EXCEPTION_COMPLETIONS_MISSING_CATEGORY = frozenset(
    {
        ("4", "get_runtime_info"),
        ("48", "save_document"),
        ("86", "check_rpc_sync"),
        ("137", "check_rpc_sync"),
        ("150", "preview_attachment"),
    }
)


def _load_inventory() -> dict[str, Any]:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _iter_mcp_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in JSONL_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("source") == "mcp":
            rows.append(row)
    return rows


def _baseline_completion_inventory() -> tuple[
    dict[str, str | None],
    list[dict[str, Any]],
    Counter[str],
]:
    received_by_call_id: dict[str, str | None] = {}
    completions: list[dict[str, Any]] = []
    generated_by_tool: Counter[str] = Counter()

    for row in _iter_mcp_rows():
        event = row.get("event")
        call_id = str(row.get("call_id"))
        payload = row.get("payload") or {}
        tool = payload.get("tool")
        category = payload.get("execution_category")

        if event == "tool_call_received":
            received_by_call_id[call_id] = category
        elif event == "tool_call_completed" and tool:
            completion = {
                "call_id": call_id,
                "tool": tool,
                "status": row.get("status"),
                "category": category,
                "payload": payload,
            }
            completions.append(completion)
            if category == "generated_internal_execute":
                generated_by_tool[tool] += 1

    return received_by_call_id, completions, generated_by_tool


def test_inventory_fixture_schema_matches_high_spec() -> None:
    inventory = _load_inventory()
    assert inventory["campaign_run_id"] == CAMPAIGN_RUN_ID
    assert inventory["candidate_head"] == CANDIDATE_HEAD
    assert inventory["d13_outcome"] == "INFO"
    assert inventory["authoritative_event"] == "tool_call_completed"
    assert inventory["tools"], "expected one row per exercised tool"

    for entry in inventory["tools"]:
        assert entry["candidate_expected_completed"] == "typed_direct_rpc"
        assert entry["match_baseline_required"] is False
        assert isinstance(entry["baseline_completed_categories"], dict)
        assert entry["candidate_reason"]


def test_inventory_fixture_covers_every_exercised_tool_in_jsonl() -> None:
    _, completions, _ = _baseline_completion_inventory()
    exercised = {row["tool"] for row in completions}
    inventory_tools = {entry["tool"] for entry in _load_inventory()["tools"]}
    assert inventory_tools == exercised


def test_inventory_fixture_matches_jsonl_completed_category_counts() -> None:
    _, completions, _ = _baseline_completion_inventory()
    observed: dict[str, Counter[str | None]] = {}
    for row in completions:
        observed.setdefault(row["tool"], Counter())[row["category"]] += 1

    for entry in _load_inventory()["tools"]:
        tool = entry["tool"]
        expected = Counter(entry["baseline_completed_categories"])
        actual = Counter({k: v for k, v in observed[tool].items() if k is not None})
        assert actual == expected, tool


def test_received_categories_are_typed_direct_rpc_except_exception_completions() -> None:
    received_by_call_id, completions, _ = _baseline_completion_inventory()
    missing_completed_category = {
        (row["call_id"], row["tool"])
        for row in completions
        if row["category"] is None
    }
    assert missing_completed_category == EXCEPTION_COMPLETIONS_MISSING_CATEGORY

    for row in completions:
        call_id = row["call_id"]
        received_category = received_by_call_id.get(call_id)
        if (call_id, row["tool"]) in EXCEPTION_COMPLETIONS_MISSING_CATEGORY:
            continue
        assert received_category == "typed_direct_rpc", (
            f"{row['tool']} call_id={call_id}"
        )


def test_baseline_generated_internal_execute_inventory() -> None:
    _, _, generated_by_tool = _baseline_completion_inventory()
    assert set(generated_by_tool) == EXPECTED_GENERATED_TOOLS
    assert sum(generated_by_tool.values()) == 74


def test_generated_internal_execute_rows_carry_analysis_metadata() -> None:
    _, completions, _ = _baseline_completion_inventory()
    worker_count = 0
    auto_count = 0

    for row in completions:
        if row["category"] != "generated_internal_execute":
            continue
        tool = row["tool"]
        analysis = row["payload"].get("analysis")
        assert isinstance(analysis, dict), tool
        assert analysis.get("code_sha256"), tool
        assert "read_only" in analysis, tool
        assert "execution_mode" in analysis, tool

        if tool in WORKER_READ_ONLY_TOOLS:
            assert analysis["read_only"] is True, tool
            assert analysis["execution_mode"] == "worker", tool
            worker_count += 1
        elif tool in AUTO_MUTATOR_TOOLS:
            assert analysis["read_only"] is False, tool
            assert analysis["execution_mode"] == "auto", tool
            auto_count += 1
        else:
            pytest.fail(f"unexpected generated_internal_execute tool: {tool}")

    assert worker_count == 47
    assert auto_count == 27


def test_execute_code_was_never_completed_in_baseline_jsonl() -> None:
    _, completions, _ = _baseline_completion_inventory()
    execute_code_completions = [row for row in completions if row["tool"] == "execute_code"]
    assert execute_code_completions == []
