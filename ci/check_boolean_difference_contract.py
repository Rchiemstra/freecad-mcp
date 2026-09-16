#!/usr/bin/env python3
"""Fast static and architecture gate for the typed ``boolean_difference`` slice."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from ci.scan_typed_feature_contract import main_for_op


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    return main_for_op("boolean_difference")


if __name__ == "__main__":
    raise SystemExit(main())
