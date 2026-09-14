"""Sensitivity checks for the ``run_fem_analysis`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_run_fem_analysis_contract import scan_run_fem_analysis_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/run_fem_analysis.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/run_fem_analysis.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_run_fem_analysis_architecture_gate_rejects_the_production_path_for_policy_reasons() -> None:
    violations = scan_run_fem_analysis_architecture(ROOT)
    assert violations != []
    assert any(item.startswith("EXT run_fem_analysis") for item in violations)

    assert any("inside native apply" in item for item in violations)
    assert any("committed/rejected" in item for item in violations)



def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_run_fem_analysis_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "RUN_FEM_ANALYSIS008 public adapter bypasses response validation" in scan_run_fem_analysis_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_run_fem_analysis_request("
    broken = "from typing import Any\n\ndef build_run_fem_analysis_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "RUN_FEM_ANALYSIS014 typed run_fem_analysis surface contains Any: run_fem_analysis leaf" in scan_run_fem_analysis_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
