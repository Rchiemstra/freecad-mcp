"""Sensitivity checks for the ``spreadsheet_get_cells`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_spreadsheet_get_cells_contract import scan_spreadsheet_get_cells_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/spreadsheet_get_cells.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/spreadsheet_get_cells.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_spreadsheet_get_cells_architecture_gate_passes_the_production_path() -> None:
    assert scan_spreadsheet_get_cells_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = source.replace(
        "    request = build_spreadsheet_get_cells_request(doc_name, sheet_name, addresses)",
        "    run_spreadsheet_get_cells_native_mutation(collaborators, \"\", lambda _d: None, lambda _d: None)\n    request = build_spreadsheet_get_cells_request(doc_name, sheet_name, addresses)",
        1,
    )
    assert any("fake mutation pipeline" in item for item in scan_spreadsheet_get_cells_architecture(
        ROOT, source_overrides={LEAF: broken},
    ))


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_spreadsheet_get_cells_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "SPREADSHEET_GET_CELLS008 public adapter bypasses response validation" in scan_spreadsheet_get_cells_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_spreadsheet_get_cells_request("
    broken = "from typing import Any\n\ndef build_spreadsheet_get_cells_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "SPREADSHEET_GET_CELLS014 typed spreadsheet_get_cells surface contains Any: spreadsheet_get_cells leaf" in scan_spreadsheet_get_cells_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
