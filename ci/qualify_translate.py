"""Repeatable acceptance lanes for the typed ``translate`` mutation."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PYTHON_TESTS = (
    "tests/test_translate.py",
    "tests/test_translate_response.py",
    "tests/test_translate_contract_gate.py",
    "tests/test_translate_json_rpc_contract.py",
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
        import FreeCAD

        if getattr(FreeCAD, "__mcp_test_stub__", False):
            raise RuntimeError("Native qualification requires a real branch-built FreeCAD")
        os.environ["FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION"] = "1"
        tests = ("tests/test_native_translate.py",)
    else:
        result = subprocess.run(
            [sys.executable, "ci/check_translate_contract.py"],
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
