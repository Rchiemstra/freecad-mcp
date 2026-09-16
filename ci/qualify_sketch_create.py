"""Repeatable acceptance lanes for the typed ``sketch_create`` implementation.

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
    "tests/sketch/test_sketch_create.py",
    "tests/sketch/test_sketch_create_response.py",
    "tests/sketch/test_sketch_create_contract_gate.py",
    "tests/test_typed_platform_discovery.py",
    "tests/sketch/test_sketch_create_json_rpc_contract.py",
    "tests/collaboration/test_collaboration_api.py",
    "tests/test_parametric.py",
    "tests/test_instrumented_server_worker.py",
    "tests/mcp/test_mcp_tasks.py",
    "tests/capability/test_capability_manifest_generator.py",
    "tests/test_generated_registration_cutover.py",
    "tests/mcp/test_mcp_tool_modules_register.py",
    "tests/phase18/test_phase18_registered_tool_runtime.py",
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
        tests = ("tests/native/test_native_sketch_create.py",)
    else:
        result = subprocess.run(
            [sys.executable, "ci/check_sketch_create_contract.py"],
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
