#!/usr/bin/env python3
"""Fast architecture gate for the typed ``sketch_trim`` slice."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from ci.typed_sketch_contract import main_for_op


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    return main_for_op("sketch_trim")


if __name__ == "__main__":
    raise SystemExit(main())
