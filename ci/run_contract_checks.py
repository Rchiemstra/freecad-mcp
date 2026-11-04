#!/usr/bin/env python3
"""Run every discovered typed-operation contract gate under ``ci/``."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from ci.discover_typed_slice import (
    TYPED_SLICE_CHECKED_ENV,
    discover_contract_check_scripts,
    run_discovered_mypy,
)


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    root = Path(__file__).resolve().parents[1]
    scripts = discover_contract_check_scripts(root)
    if not scripts:
        print("typed contract checks: no check_*_contract.py scripts found", file=sys.stderr)
        return 1

    # A flag inherited from the caller must not skip the one real typecheck.
    os.environ.pop(TYPED_SLICE_CHECKED_ENV, None)
    print("typed contract checks: typechecking the typed slice once for every gate")
    mypy_result = run_discovered_mypy(root, retry_internal_error=True)
    if mypy_result:
        return mypy_result

    gate_env = {**os.environ, TYPED_SLICE_CHECKED_ENV: "1"}
    for script in scripts:
        print(f"typed contract checks: running {script.relative_to(root).as_posix()}")
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=root,
            check=False,
            env=gate_env,
        )
        if result.returncode:
            return result.returncode

    print(f"typed contract checks: OK ({len(scripts)} gate(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
