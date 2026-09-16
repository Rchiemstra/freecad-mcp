"""Sensitivity checks for the ``export_brep`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_export_brep_contract import scan_export_brep_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/export_brep.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/export_brep.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_export_brep_architecture_gate_passes_the_production_path() -> None:
    assert scan_export_brep_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = "def apply_export_brep():\n    measure_io_actions.export_brep\n" + source
    assert any("external effect inside native apply" in item for item in scan_export_brep_architecture(
        ROOT, source_overrides={LEAF: broken},
    ))


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_export_brep_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "EXPORT_BREP008 public adapter bypasses response validation" in scan_export_brep_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_export_brep_request("
    broken = "from typing import Any\n\ndef build_export_brep_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "EXPORT_BREP014 typed export_brep surface contains Any: export_brep leaf" in scan_export_brep_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
