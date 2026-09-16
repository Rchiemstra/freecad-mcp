"""Sensitivity checks for the build_path_wire static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_build_path_wire_contract import scan_build_path_wire_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/build_path_wire.py"
MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/build_path_wire_mutation.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/build_path_wire.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_build_path_wire_architecture_gate_accepts_the_production_path() -> None:
    assert scan_build_path_wire_architecture(ROOT) == []


def test_gate_rejects_inspection_before_recompute() -> None:
    source = _read(LEAF)
    old = "            self.inspect,"
    assert source.count(old) == 1
    mutated = source.replace(old, "            self.apply,")
    assert "BUILD_PATH_WIRE004 missing typed postcondition=inspect" in scan_build_path_wire_architecture(
        ROOT, source_overrides={LEAF: mutated}
    )


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_build_path_wire_response(raw_result)"
    assert source.count(old) == 1
    mutated = source.replace(old, "result = raw_result")
    assert "BUILD_PATH_WIRE008 public adapter bypasses response validation" in scan_build_path_wire_architecture(
        ROOT, source_overrides={PUBLIC_ADAPTER: mutated}
    )


def test_gate_rejects_cached_success_after_native_rejection() -> None:
    source = _read(MUTATION)
    old = "    if committed is not False or status not in _REJECTED_STATUSES:"
    assert source.count(old) == 1
    mutated = source.replace(
        old,
        "    if state.postcondition_passed:\n        return True\n    if committed is not False or status not in _REJECTED_STATUSES:",
    )
    assert "BUILD_PATH_WIRE007 cached success escaped native rejection" in scan_build_path_wire_architecture(
        ROOT, source_overrides={MUTATION: mutated}
    )


def test_gate_rejects_any_on_the_leaf() -> None:
    source = _read(LEAF)
    old = "def build_build_path_wire_request("
    assert source.count(old) == 1
    mutated = source.replace(old, "from typing import Any\n\ndef build_build_path_wire_request(", 1)
    # Force an explicit Any on the leaf surface.
    mutated = mutated.replace("doc_name: object", "doc_name: Any", 1)
    assert any("Any" in item for item in scan_build_path_wire_architecture(ROOT, source_overrides={LEAF: mutated}))
