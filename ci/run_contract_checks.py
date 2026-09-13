#!/usr/bin/env python3
"""Run every discovered typed-operation contract gate under ``ci/``."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from ci.discover_typed_slice import discover_contract_check_scripts


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    root = Path(__file__).resolve().parents[1]
    scripts = discover_contract_check_scripts(root)
    if not scripts:
        print("typed contract checks: no check_*_contract.py scripts found", file=sys.stderr)
        return 1

    for script in scripts:
        print(f"typed contract checks: running {script.relative_to(root).as_posix()}")
        result = subprocess.run([sys.executable, str(script)], cwd=root, check=False)
        if result.returncode:
            return result.returncode

    print(f"typed contract checks: OK ({len(scripts)} gate(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
