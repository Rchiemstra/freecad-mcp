#!/usr/bin/env python3
"""Merge per-process telemetry JSONL files into deterministic time order."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def read_events(paths: Iterable[Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{line_number}: event is not an object")
                value.setdefault("_source_file", path.name)
                events.append(value)
    return sorted(
        events,
        key=lambda item: (
            str(item.get("timestamp") or ""),
            str(item.get("session_id") or ""),
            int(item.get("sequence") or 0),
        ),
    )


def merge(paths: Iterable[Path], output: Path) -> int:
    events = read_events(paths)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    return len(events)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    args = parser.parse_args()
    count = merge(args.inputs, args.output)
    print(f"Merged {count} events into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
