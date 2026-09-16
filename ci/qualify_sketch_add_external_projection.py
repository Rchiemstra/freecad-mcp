"""Repeatable acceptance lanes for the typed ``sketch_add_external_projection`` mutation."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PYTHON_TESTS = (
    "tests/sketch/test_sketch_add_external_projection.py",
    "tests/sketch/test_sketch_add_external_projection_response.py",
    "tests/sketch/test_sketch_add_external_projection_contract_gate.py",
    "tests/sketch/test_sketch_add_external_projection_json_rpc_contract.py",
    "tests/test_typed_platform_discovery.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "src"))
    if args.native:
        try:
            import FreeCAD
            import PartDesign  # noqa: F401 - initialize native module before pytest
        except ImportError as exc:
            raise RuntimeError("Native qualification requires a real branch-built FreeCAD") from exc
        if getattr(FreeCAD, "__mcp_test_stub__", False):
            raise RuntimeError("Native qualification requires a real branch-built FreeCAD")
        os.environ["FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION"] = "1"
        tests = ("tests/native/test_native_sketch_add_external_projection.py",)
    else:
        result = subprocess.run(
            [sys.executable, "ci/check_sketch_add_external_projection_contract.py"],
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
