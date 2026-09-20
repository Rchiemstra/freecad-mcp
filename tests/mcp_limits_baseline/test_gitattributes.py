#!/usr/bin/env python3
"""Checkout-stability guards for MCP limits baseline gitattributes."""

from __future__ import annotations

import fnmatch
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
GITATTRIBUTES = REPO_ROOT / ".gitattributes"
BASELINE_ROOT = "tests/mcp_limits_baseline"

GOLDEN_FIXTURE_PATHS = (
    f"{BASELINE_ROOT}/fixtures/REPORT.md",
    f"{BASELINE_ROOT}/fixtures/findings-log.md",
    f"{BASELINE_ROOT}/fixtures/coverage-matrix.md",
    f"{BASELINE_ROOT}/fixtures/reproductions.md",
    f"{BASELINE_ROOT}/fixtures/results.json",
    f"{BASELINE_ROOT}/fixtures/mcp_debug_2026-09-16_317891_0a5ddd947d58.jsonl",
)


def _parse_gitattributes(path: Path) -> list[tuple[str, str]]:
    rules: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pattern, attrs = stripped.split(None, 1)
        rules.append((pattern, attrs))
    return rules


def _gitattributes_matches(pattern: str, path: str) -> bool:
    normalized = path.replace("\\", "/")
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return normalized == prefix or normalized.startswith(f"{prefix}/")
    return fnmatch.fnmatch(normalized, pattern)


def _effective_gitattributes(path: str, rules: list[tuple[str, str]]) -> str:
    matched: list[str] = []
    for pattern, attrs in rules:
        if _gitattributes_matches(pattern, path):
            matched.append(attrs)
    if not matched:
        return ""
    return matched[-1]


def test_gitattributes_pins_golden_campaign_fixtures_to_lf() -> None:
    assert GITATTRIBUTES.is_file(), ".gitattributes must exist for checkout-stable fixtures"
    rules = _parse_gitattributes(GITATTRIBUTES)
    for fixture_path in GOLDEN_FIXTURE_PATHS:
        attrs = _effective_gitattributes(fixture_path, rules)
        assert "text" in attrs.split(), fixture_path
        assert "eol=lf" in attrs.split(), fixture_path


def test_gitattributes_pins_entire_mcp_limits_baseline_harness_to_lf() -> None:
    rules = _parse_gitattributes(GITATTRIBUTES)
    harness_paths = (
        f"{BASELINE_ROOT}/checksums.py",
        f"{BASELINE_ROOT}/fixtures/golden_sha256.json",
        f"{BASELINE_ROOT}/fixtures/intended_bases.json",
        f"{BASELINE_ROOT}/test_campaign_evidence.py",
    )
    for harness_path in harness_paths:
        attrs = _effective_gitattributes(harness_path, rules)
        assert "text" in attrs.split(), harness_path
        assert "eol=lf" in attrs.split(), harness_path
