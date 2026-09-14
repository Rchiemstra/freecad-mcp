"""Sensitivity checks for the ``create_document`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_create_document_contract import scan_create_document_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/create_document.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/create_document.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_create_document_architecture_gate_rejects_the_production_path_for_policy_reasons() -> None:
    violations = scan_create_document_architecture(ROOT)
    assert violations != []
    assert any(item.startswith("LIFE create_document") for item in violations)

    assert any("mutation pipeline as perform step" in item for item in violations)
    assert any("committed" in item for item in violations)



def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_create_document_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "CREATE_DOCUMENT008 public adapter bypasses response validation" in scan_create_document_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_create_document_request("
    broken = "from typing import Any\n\ndef build_create_document_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "CREATE_DOCUMENT014 typed create_document surface contains Any: create_document leaf" in scan_create_document_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
