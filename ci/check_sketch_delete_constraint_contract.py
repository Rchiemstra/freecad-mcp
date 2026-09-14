#!/usr/bin/env python3
"""Fast static and architecture gate for the typed ``sketch_delete_constraint`` slice."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from ci.scan_execution_policy_gates import scan_op_architecture
from ci.scan_typed_feature_contract import main_for_op as _main_for_op


def scan_sketch_delete_constraint_architecture(
    root: Path,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    return scan_op_architecture(root, "sketch_delete_constraint", source_overrides=source_overrides)


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    return _main_for_op("sketch_delete_constraint", typecheck=True)


if __name__ == "__main__":
    raise SystemExit(main())
