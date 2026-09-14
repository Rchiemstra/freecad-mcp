"""Sensitivity checks for the export_stl static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_export_stl_contract import scan_export_stl_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/export_stl.py"
MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/export_stl_mutation.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/export_stl.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_export_stl_architecture_gate_accepts_the_production_path() -> None:
    assert scan_export_stl_architecture(ROOT) == []


def test_gate_rejects_missing_inspect_postcondition() -> None:
    source = _read(LEAF)
    old = "            self.inspect,"
    broken = "            self.apply,"
    assert source.count(old) == 1
    assert "EXPORT_STL004 missing typed postcondition=inspect" in scan_export_stl_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken)},
    )


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_export_stl_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "EXPORT_STL008 public adapter bypasses response validation" in scan_export_stl_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_transaction_or_recompute_ownership_in_the_leaf() -> None:
    source = _read(LEAF)
    marker = '    """Apply export_stl without recomputing or managing a transaction."""'
    assert source.count(marker) == 1
    mutated = source.replace(marker, marker + "\n\n    doc.recompute()")
    assert "EXPORT_STL001 leaf owns forbidden execution: recompute" in (
        scan_export_stl_architecture(ROOT, source_overrides={LEAF: mutated})
    )


def test_gate_rejects_cached_success_after_native_rejection() -> None:
    source = _read(MUTATION)
    old = "    if committed is not False or status not in _REJECTED_STATUSES:"
    broken = "    if state.postcondition_passed:\n        return True\n    if committed is not False or status not in _REJECTED_STATUSES:"
    assert source.count(old) == 1
    assert "EXPORT_STL007 cached success escaped native rejection" in scan_export_stl_architecture(
        ROOT,
        source_overrides={MUTATION: source.replace(old, broken)},
    )
