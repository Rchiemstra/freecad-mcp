"""Sensitivity checks for the ``export_step`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_export_step_contract import scan_export_step_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/export_step.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/export_step.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_export_step_architecture_gate_passes_the_production_path() -> None:
    assert scan_export_step_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = "def apply_export_step():\n    measure_io_actions.export_step\n" + source
    assert any("external effect inside native apply" in item for item in scan_export_step_architecture(
        ROOT, source_overrides={LEAF: broken},
    ))


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_export_step_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "EXPORT_STEP008 public adapter bypasses response validation" in scan_export_step_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_export_step_request("
    broken = "from typing import Any\n\ndef build_export_step_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "EXPORT_STEP014 typed export_step surface contains Any: export_step leaf" in scan_export_step_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
