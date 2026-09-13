"""Sensitivity checks for the sketch_add_external_projection static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_sketch_add_external_projection_contract import scan_sketch_add_external_projection_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/sketch_add_external_projection.py"
MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/sketch_add_external_projection_mutation.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/sketch_add_external_projection.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_sketch_add_external_projection_architecture_gate_accepts_the_production_path() -> None:
    assert scan_sketch_add_external_projection_architecture(ROOT) == []


def test_gate_rejects_inspection_before_recompute() -> None:
    source = _read(LEAF)
    old = "            self.inspect,"
    assert source.count(old) == 1
    mutated = source.replace(old, "            self.apply,")
    assert "SKETCH_ADD_EXTERNAL_PROJECTION004 missing typed postcondition=inspect" in scan_sketch_add_external_projection_architecture(
        ROOT, source_overrides={LEAF: mutated}
    )


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_sketch_add_external_projection_response(raw_result)"
    assert source.count(old) == 1
    mutated = source.replace(old, "result = raw_result")
    assert "SKETCH_ADD_EXTERNAL_PROJECTION008 public adapter bypasses response validation" in scan_sketch_add_external_projection_architecture(
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
    assert "SKETCH_ADD_EXTERNAL_PROJECTION007 cached success escaped native rejection" in scan_sketch_add_external_projection_architecture(
        ROOT, source_overrides={MUTATION: mutated}
    )


def test_gate_rejects_any_on_the_leaf() -> None:
    source = _read(LEAF)
    old = "def build_sketch_add_external_projection_request("
    assert source.count(old) == 1
    mutated = source.replace(old, "from typing import Any\n\ndef build_sketch_add_external_projection_request(", 1)
    # Force an explicit Any on the leaf surface.
    mutated = mutated.replace("doc_name: object", "doc_name: Any", 1)
    assert any("Any" in item for item in scan_sketch_add_external_projection_architecture(ROOT, source_overrides={LEAF: mutated}))
