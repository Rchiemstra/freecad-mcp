"""Run pytest without presenting ``SystemExit(0)`` to FreeCAD's C teardown.

Some FreeCAD/PySide object graphs turn the console script's otherwise successful
``SystemExit(0)`` into a late process status of one during extension shutdown.
Returning normally for pytest's zero status avoids that false failure. Every
non-zero pytest status is still raised, so collection and test failures remain
hard Docker failures even if extension teardown normalizes the final code.
"""

from __future__ import annotations

import sys

import pytest


def main() -> None:
    exit_code = int(pytest.main(sys.argv[1:]))
    if exit_code != 0:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
