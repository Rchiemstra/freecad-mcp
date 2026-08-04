#!/usr/bin/env python3
"""Preserve pytest's logical result across FreeCAD's C teardown.

Some FreeCAD/PySide object graphs turn the console script's otherwise successful
result into a late process status of one during extension shutdown. Pytest runs in
a child process and records its result before that teardown. The clean parent then
returns the recorded result, while missing results, signals, collection failures,
and test failures remain hard Docker failures.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

_CHILD_ENV = "FREECAD_MCP_PYTEST_ENTRYPOINT_CHILD"
_RESULT_ENV = "FREECAD_MCP_PYTEST_ENTRYPOINT_RESULT"


def _run_pytest_child() -> None:
    import pytest

    exit_code = int(pytest.main(sys.argv[1:]))
    result_path = Path(os.environ[_RESULT_ENV])
    result_path.write_text(str(exit_code), encoding="ascii")
    if exit_code != 0:
        raise SystemExit(exit_code)


def main() -> None:
    if os.environ.get(_CHILD_ENV) == "1":
        _run_pytest_child()
        return

    with tempfile.TemporaryDirectory(prefix="freecad-mcp-pytest-") as temporary_dir:
        result_path = Path(temporary_dir, "result")
        environment = os.environ.copy()
        environment[_CHILD_ENV] = "1"
        environment[_RESULT_ENV] = str(result_path)
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
            check=False,
            env=environment,
        )
        try:
            exit_code = int(result_path.read_text(encoding="ascii"))
        except (OSError, ValueError):
            raise SystemExit(completed.returncode or 1) from None

    if exit_code != 0:
        raise SystemExit(exit_code)
    if completed.returncode not in (0, 1):
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
