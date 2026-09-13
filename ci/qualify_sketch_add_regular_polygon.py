"""Repeatable acceptance lanes for the typed ``sketch_add_regular_polygon`` mutation."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PYTHON_TESTS = (
    "tests/test_sketch_add_regular_polygon.py",
    "tests/test_sketch_add_regular_polygon_response.py",
    "tests/test_sketch_add_regular_polygon_contract_gate.py",
    "tests/test_sketch_add_regular_polygon_json_rpc_contract.py",
    "tests/test_typed_platform_discovery.py",
    "tests/test_body_create.py",
    "tests/test_body_create_response.py",
    "tests/test_body_create_contract_gate.py",
    "tests/test_body_create_json_rpc_contract.py",
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
        import Part  # noqa: F401
        import PartDesign  # noqa: F401
        import Sketcher  # noqa: F401

        if getattr(FreeCAD, "__mcp_test_stub__", False):
            raise RuntimeError("Native qualification requires a real branch-built FreeCAD")
        os.environ["FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION"] = "1"
        tests = ("tests/test_native_sketch_add_regular_polygon.py",)
    else:
        result = subprocess.run(
            [sys.executable, "ci/check_sketch_add_regular_polygon_contract.py"],
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
