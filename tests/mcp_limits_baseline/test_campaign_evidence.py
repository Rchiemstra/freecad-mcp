#!/usr/bin/env python3
"""Regression harness for the run-20260916-mcp-limits campaign evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.mcp_limits_baseline.checksums import assert_file_sha256, sha256_hex

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CAMPAIGN_RUN_ID = "run-20260916-mcp-limits"

GOLDEN_FILES = (
    "REPORT.md",
    "findings-log.md",
    "coverage-matrix.md",
    "reproductions.md",
    "results.json",
    "mcp_debug_2026-09-16_317891_0a5ddd947d58.jsonl",
)

BASELINE_DEFECT_OUTCOMES = {
    "D-01": "FAIL",
    "D-02": "CAPABILITY_GAP",
    "D-03": "FAIL",
    "D-04": "FAIL",
    "D-05": "FAIL",
    "D-06": "FAIL",
    "D-07": "CAPABILITY_GAP",
    "D-08": "FAIL",
    "D-09": "OBSERVABILITY_GAP",
    "D-10": "OBSERVABILITY_GAP",
    "D-11": "OBSERVABILITY_GAP",
    "D-12": "FAIL",
    "D-13": "INFO",
    "D-14": "CAPABILITY_GAP",
}

ALLOWED_NATIVE_APPLICABILITY = frozenset({"N/A", "NOT_TESTED"})

_SECRET_KEY_PATTERN = re.compile(
    r"(?:^|[_-])(secret|password|token|authorization)(?:$|[_-])",
    re.IGNORECASE,
)
_REDACTED_VALUES = frozenset(
    {
        "",
        "unknown",
        "<redacted>",
        "<stored separately; contents not printed>",
    }
)


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _load_results() -> dict[str, Any]:
    return _load_json("results.json")


def _findings_text() -> str:
    return (FIXTURES / "findings-log.md").read_text(encoding="utf-8")


def _reproductions_text() -> str:
    return (FIXTURES / "reproductions.md").read_text(encoding="utf-8")


def _iter_json_objects(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        objects: list[dict[str, Any]] = []
        for item in value:
            objects.extend(_iter_json_objects(item))
        return objects
    return []


def _collect_secret_like_violations(value: Any, *, path: str = "") -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if (
                isinstance(key, str)
                and _SECRET_KEY_PATTERN.search(key)
                and not _is_redacted_secret_value(nested)
            ):
                violations.append(child_path)
            violations.extend(
                _collect_secret_like_violations(nested, path=child_path)
            )
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            violations.extend(
                _collect_secret_like_violations(nested, path=f"{path}[{index}]")
            )
    return violations


def _is_redacted_secret_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in _REDACTED_VALUES:
            return True
        if normalized.startswith("<") and normalized.endswith(">"):
            return True
        return normalized.startswith(("hmac-sha256:", "sha256:"))
    return isinstance(value, (bool, int, float))


def test_vendored_campaign_files_match_golden_sha256() -> None:
    golden = _load_json("golden_sha256.json")
    assert golden["campaign_run_id"] == CAMPAIGN_RUN_ID
    for name in GOLDEN_FILES:
        assert_file_sha256(FIXTURES / name, golden["files"][name])


def test_checksum_helper_rejects_one_byte_mutation(tmp_path: Path) -> None:
    source = FIXTURES / "results.json"
    copy = tmp_path / "results.json"
    copy.write_bytes(source.read_bytes())
    expected = sha256_hex(copy)
    data = bytearray(copy.read_bytes())
    data[0] ^= 0x01
    copy.write_bytes(bytes(data))
    with pytest.raises(AssertionError, match="checksum mismatch"):
        assert_file_sha256(copy, expected)


def test_results_json_run_id() -> None:
    results = _load_results()
    assert results["run_id"] == CAMPAIGN_RUN_ID


def test_results_json_records_baseline_defect_classifications() -> None:
    results = _load_results()
    recorded = {entry["id"]: entry["outcome"] for entry in results["defects"]}
    assert set(recorded) == set(BASELINE_DEFECT_OUTCOMES)
    for defect_id, expected_outcome in BASELINE_DEFECT_OUTCOMES.items():
        assert recorded[defect_id] == expected_outcome


def test_findings_log_records_f05_observability_gap_without_fix_claim() -> None:
    text = _findings_text()
    assert "## F-05 OBSERVABILITY_GAP" in text
    assert "build identity not tied to a commit" in text
    assert re.search(r"F-05[^\n]*\bFIXED\b", text, re.IGNORECASE) is None
    assert re.search(r"F-05[^\n]*\bRESOLVED\b", text, re.IGNORECASE) is None


def test_f10_pass_expected_rejection_distinct_from_d06_get_object_null() -> None:
    findings = _findings_text()
    reproductions = _reproductions_text()
    results = _load_results()

    assert "## F-10 PASS_EXPECTED_REJECTION" in findings
    assert "NameError" in findings
    assert "stale document handle" in findings

    d06 = next(item for item in results["defects"] if item["id"] == "D-06")
    assert d06["outcome"] == "FAIL"
    assert "succeeded" in d06["title"].lower()
    assert "nonexistent object" in d06["title"].lower()

    assert "## R-04 · D-06" in reproductions
    assert '"status": "succeeded"' in reproductions
    assert '"value": null' in reproductions

    assert "PASS_EXPECTED_REJECTION" not in d06["title"]
    assert "NameError" not in d06["title"]


def test_native_applicability_never_labels_pass() -> None:
    fixture = _load_json("native_applicability.json")
    assert fixture["campaign_run_id"] == CAMPAIGN_RUN_ID
    for defect_id, status in fixture["defects"].items():
        assert status in ALLOWED_NATIVE_APPLICABILITY, (
            f"{defect_id} must stay N/A or NOT_TESTED, not {status!r}"
        )
        assert status != "PASS"


def test_intended_bases_documentation_is_honest_about_loaded_runtime() -> None:
    fixture = _load_json("intended_bases.json")
    assert fixture["campaign_run_id"] == CAMPAIGN_RUN_ID
    assert fixture["bases"]["integration_typed_rpc"]["pin"] == (
        "ce8ac37fa9d99b6304312d9be36315acf78e2d6c"
    )
    assert fixture["bases"]["mcp"]["pin"] == (
        "ce8ac37fa9d99b6304312d9be36315acf78e2d6c"
    )
    assert fixture["bases"]["freecad_start"]["pin"] == (
        "8f3bef65dafd3e414781c3f6e416c2e9aca907ed"
    )
    loaded = fixture["loaded_runtime"]
    assert loaded["status"] == "unknown"
    assert loaded["freecad_binary"] is None
    assert loaded["freecad_commit"] is None
    assert loaded["mcp_commit"] is None


def test_evidence_system_schema_44_is_a_different_harness() -> None:
    preflight = (
        Path(__file__).resolve().parents[1]
        / "evidence_system"
        / "test_preflight_schema.py"
    ).read_text(encoding="utf-8")
    assert 'run_id="P3-WP27"' in preflight
    assert "sequence=44" in preflight
    assert CAMPAIGN_RUN_ID not in preflight


def test_campaign_jsonl_has_no_unredacted_secret_like_keys() -> None:
    jsonl_path = FIXTURES / "mcp_debug_2026-09-16_317891_0a5ddd947d58.jsonl"
    violations: list[str] = []
    for line_number, line in enumerate(
        jsonl_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        payload = json.loads(line)
        for path in _collect_secret_like_violations(payload):
            violations.append(f"line {line_number}: {path}")
    assert violations == []


def test_product_gaps_remain_open_in_baseline_evidence() -> None:
    results = _load_results()
    open_outcomes = {"FAIL", "CAPABILITY_GAP", "OBSERVABILITY_GAP", "INFO"}
    for defect_id in BASELINE_DEFECT_OUTCOMES:
        entry = next(item for item in results["defects"] if item["id"] == defect_id)
        assert entry["outcome"] in open_outcomes
        assert entry["outcome"] != "PASS"
