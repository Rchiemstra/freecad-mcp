"""Sensitivity checks for the ``center_of_mass`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_center_of_mass_contract import scan_center_of_mass_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/center_of_mass.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/center_of_mass.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_center_of_mass_architecture_gate_passes_the_production_path() -> None:
    assert scan_center_of_mass_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = source.replace(
        "    request = build_center_of_mass_request(doc_name, obj_name)",
        "    run_center_of_mass_native_mutation(collaborators, \"\", lambda _d: None, lambda _d: None)\n    request = build_center_of_mass_request(doc_name, obj_name)",
        1,
    )
    assert any("fake mutation pipeline" in item for item in scan_center_of_mass_architecture(
        ROOT, source_overrides={LEAF: broken},
    ))


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_center_of_mass_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "CENTER_OF_MASS008 public adapter bypasses response validation" in scan_center_of_mass_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_center_of_mass_request("
    broken = "from typing import Any\n\ndef build_center_of_mass_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "CENTER_OF_MASS014 typed center_of_mass surface contains Any: center_of_mass leaf" in scan_center_of_mass_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
