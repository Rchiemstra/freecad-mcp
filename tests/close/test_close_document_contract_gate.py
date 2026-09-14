"""Sensitivity checks for the ``close_document`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_close_document_contract import scan_close_document_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/close_document.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/close_document.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_close_document_architecture_gate_rejects_the_production_path_for_policy_reasons() -> None:
    violations = scan_close_document_architecture(ROOT)
    assert violations != []
    assert any(item.startswith("LIFE close_document") for item in violations)

    assert any("mutation pipeline as perform step" in item for item in violations)
    assert any("committed" in item for item in violations)



def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_close_document_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "CLOSE_DOCUMENT008 public adapter bypasses response validation" in scan_close_document_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_close_document_request("
    broken = "from typing import Any\n\ndef build_close_document_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "CLOSE_DOCUMENT014 typed close_document surface contains Any: close_document leaf" in scan_close_document_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
