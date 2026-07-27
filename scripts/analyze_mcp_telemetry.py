#!/usr/bin/env python3
"""Summarize lifecycle completeness and execute-code adoption from JSONL."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from typing import Any, Iterable


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[rank]


def analyze(paths: Iterable[Path]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            events.extend(
                value
                for line in handle
                if line.strip()
                for value in (json.loads(line),)
                if isinstance(value, dict)
            )
    event_counts = Counter(str(item.get("event") or "unknown") for item in events)
    status_counts = Counter(str(item.get("status") or "unknown") for item in events)
    categories: Counter[str] = Counter()
    public_patterns: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "imports": set(),
            "operations": set(),
            "document_scopes": set(),
            "access_modes": Counter(),
            "execution_modes": Counter(),
            "execution_targets": Counter(),
            "outcomes": Counter(),
            "latencies_ms": [],
            "typed_tool_suggestions": set(),
            "source_hashes": set(),
        }
    )
    for event in events:
        if event.get("event") != "tool_call_completed":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        category = payload.get("execution_category")
        if category:
            categories[str(category)] += 1
        analysis = payload.get("analysis")
        if category != "public_execute_code" or not isinstance(analysis, dict):
            continue
        key = str(analysis.get("ast_pattern_hash") or "unparsed")
        group = public_patterns[key]
        group["calls"] += 1
        group["imports"].update(
            str(item) for item in analysis.get("imports") or ()
        )
        group["operations"].update(
            str(item) for item in analysis.get("call_families") or ()
        )
        group["document_scopes"].add(
            tuple(str(item) for item in analysis.get("document_scope") or ())
        )
        group["access_modes"][
            "read_only" if analysis.get("read_only") else "mutating"
        ] += 1
        execution_mode = str(analysis.get("execution_mode") or "auto")
        group["execution_modes"][execution_mode] += 1
        execution_target = (
            "worker"
            if analysis.get("read_only") or execution_mode == "worker"
            else "gui"
        )
        group["execution_targets"][execution_target] += 1
        outcome = str(event.get("status") or "unknown")
        group["outcomes"][outcome] += 1
        duration = event.get("duration_ms")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            group["latencies_ms"].append(float(duration))
        group["typed_tool_suggestions"].update(
            str(item) for item in analysis.get("typed_tool_suggestions") or ()
        )
        source_hash = analysis.get("code_sha256")
        if source_hash:
            group["source_hashes"].add(str(source_hash))
    call_total = sum(categories.values())
    patterns = []
    for key, value in sorted(
        public_patterns.items(),
        key=lambda pair: (-pair[1]["calls"], pair[0]),
    ):
        latency_values = value["latencies_ms"]
        outcomes = value["outcomes"]
        failures = sum(
            count
            for status, count in outcomes.items()
            if status
            not in {
                "succeeded",
                "condition_false",
                "warning",
            }
        )
        patterns.append({
            "ast_pattern_hash": key,
            "calls": value["calls"],
            "imports": sorted(value["imports"]),
            "operations": sorted(value["operations"]),
            "document_scopes": [
                list(scope) for scope in sorted(value["document_scopes"])
            ],
            "access_modes": dict(sorted(value["access_modes"].items())),
            "execution_modes": dict(sorted(value["execution_modes"].items())),
            "execution_targets": dict(
                sorted(value["execution_targets"].items())
            ),
            "outcomes": dict(sorted(outcomes.items())),
            "successes": outcomes["succeeded"],
            "failures": failures,
            "timeouts": outcomes["timed_out"],
            "latency_ms": {
                "average": (
                    sum(latency_values) / len(latency_values)
                    if latency_values
                    else None
                ),
                "p50": _percentile(latency_values, 0.50),
                "p95": _percentile(latency_values, 0.95),
            },
            "typed_tool_suggestions": sorted(value["typed_tool_suggestions"]),
            "source_hashes": sorted(value["source_hashes"]),
        })
    return {
        "schema_version": 1,
        "event_count": len(events),
        "session_count": len(
            {str(item.get("session_id")) for item in events if item.get("session_id")}
        ),
        "events": dict(sorted(event_counts.items())),
        "statuses": dict(sorted(status_counts.items())),
        "execution_categories": dict(sorted(categories.items())),
        "public_execute_code_share": (
            categories["public_execute_code"] / call_total if call_total else 0.0
        ),
        "typed_tool_share": (
            categories["typed_direct_rpc"] / call_total if call_total else 0.0
        ),
        "public_execute_patterns": patterns,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    report = analyze(args.inputs)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
