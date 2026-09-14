"""Sensitivity checks for the ``redo`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_redo_contract import scan_redo_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/redo.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/redo.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_redo_architecture_gate_rejects_the_production_path_for_policy_reasons() -> None:
    violations = scan_redo_architecture(ROOT)
    assert violations != []
    assert any(item.startswith("HIST redo") for item in violations)

    assert any("model split" in item for item in violations)
    assert any("native_mutation" in item for item in violations)



def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_redo_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "REDO008 public adapter bypasses response validation" in scan_redo_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_redo_request("
    broken = "from typing import Any\n\ndef build_redo_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "REDO014 typed redo surface contains Any: redo leaf" in scan_redo_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
