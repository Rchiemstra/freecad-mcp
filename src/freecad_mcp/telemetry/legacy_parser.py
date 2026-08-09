"""Migration-only parser for pre-schema mixed debug transcripts."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any


def parse_legacy_lines(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            yield {
                "legacy": True,
                "line_number": line_number,
                "text": line[:4096],
            }
            continue
        if isinstance(value, dict):
            yield value
        else:
            yield {
                "legacy": True,
                "line_number": line_number,
                "value": value,
            }


def parse_legacy_file(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        return list(parse_legacy_lines(handle))


__all__ = ["parse_legacy_file", "parse_legacy_lines"]
