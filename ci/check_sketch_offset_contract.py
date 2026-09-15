#!/usr/bin/env python3
"""Fast architecture gate for the typed ``sketch_offset`` slice."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from ci.discover_typed_slice import run_discovered_mypy
from ci.scan_typed_feature_contract import main_for_op


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    op = "sketch_offset"
    gate_result = main_for_op(op, typecheck=False)
    if gate_result:
        return gate_result
    typecheck_result = run_discovered_mypy(_ROOT, retry_internal_error=True)
    if typecheck_result:
        return typecheck_result
    print(f"{op} contract: architecture and static types passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
