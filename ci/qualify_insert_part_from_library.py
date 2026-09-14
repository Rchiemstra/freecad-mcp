"""Repeatable acceptance lanes for typed ``insert_part_from_library``.

Run with the project interpreter for static/adapter/MCP checks. Use --native
with the branch-built FreeCAD modules on PYTHONPATH for native qualification.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PYTHON_TESTS = (
    "tests/insert/test_insert_part_from_library.py",
    "tests/insert/test_insert_part_from_library_response.py",
    "tests/insert/test_insert_part_from_library_contract_gate.py",
    "tests/insert/test_insert_part_from_library_json_rpc_contract.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "src"))
    if args.native:
        import FreeCAD

        if getattr(FreeCAD, "__mcp_test_stub__", False):
            raise RuntimeError("Native qualification requires a real branch-built FreeCAD")
        os.environ["FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION"] = "1"
        tests = ("tests/native/test_native_insert_part_from_library.py",)
    else:
        result = subprocess.run(
            [sys.executable, "ci/check_insert_part_from_library_contract.py"],
            cwd=root,
            check=False,
        )
        if result.returncode:
            return result.returncode
        tests = PYTHON_TESTS

    import pytest

    return pytest.main(
        [
            *(str(root / path) for path in tests),
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
