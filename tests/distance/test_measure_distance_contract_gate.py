"""Sensitivity checks for the ``measure_distance`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_measure_distance_contract import scan_measure_distance_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/measure_distance.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/measure_distance.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_measure_distance_architecture_gate_passes_the_production_path() -> None:
    assert scan_measure_distance_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = source.replace(
        "    request = build_measure_distance_request(doc_name, shape1_ref, shape2_ref)",
        "    run_measure_distance_native_mutation(collaborators, \"\", lambda _d: None, lambda _d: None)\n    request = build_measure_distance_request(doc_name, shape1_ref, shape2_ref)",
        1,
    )
    assert any("fake mutation pipeline" in item for item in scan_measure_distance_architecture(
        ROOT, source_overrides={LEAF: broken},
    ))


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_measure_distance_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "MEASURE_DISTANCE008 public adapter bypasses response validation" in scan_measure_distance_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_measure_distance_request("
    broken = "from typing import Any\n\ndef build_measure_distance_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "MEASURE_DISTANCE014 typed measure_distance surface contains Any: measure_distance leaf" in scan_measure_distance_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
