"""Sensitivity checks for the ``measure_volume`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_measure_volume_contract import scan_measure_volume_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/measure_volume.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/measure_volume.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_measure_volume_architecture_gate_passes_the_production_path() -> None:
    assert scan_measure_volume_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = source.replace(
        "    request = build_measure_volume_request(doc_name, obj_name)",
        "    run_measure_volume_native_mutation(collaborators, \"\", lambda _d: None, lambda _d: None)\n    request = build_measure_volume_request(doc_name, obj_name)",
        1,
    )
    assert any("fake mutation pipeline" in item for item in scan_measure_volume_architecture(
        ROOT, source_overrides={LEAF: broken},
    ))


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_measure_volume_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "MEASURE_VOLUME008 public adapter bypasses response validation" in scan_measure_volume_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_measure_volume_request("
    broken = "from typing import Any\n\ndef build_measure_volume_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "MEASURE_VOLUME014 typed measure_volume surface contains Any: measure_volume leaf" in scan_measure_volume_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
