#!/usr/bin/env python3
"""Fast static and architecture gate for the typed ``recompute_and_wait`` slice."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from ci.scan_execution_policy_gates import scan_op_architecture
from ci.scan_typed_feature_contract import main_for_op as _main_for_op


def scan_recompute_and_wait_architecture(
    root: Path,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    return scan_op_architecture(root, "recompute_and_wait", source_overrides=source_overrides)


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    return _main_for_op("recompute_and_wait", typecheck=False)


if __name__ == "__main__":
    raise SystemExit(main())
