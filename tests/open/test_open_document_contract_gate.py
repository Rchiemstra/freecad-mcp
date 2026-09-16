"""Sensitivity checks for the ``open_document`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_open_document_contract import scan_open_document_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/open_document.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/open_document.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_open_document_architecture_gate_passes_the_production_path() -> None:
    assert scan_open_document_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = source.replace(
        "    request = build_open_document_request(path)",
        '    _ = "openDocument"\n    request = build_open_document_request(path)',
        1,
    )
    assert any("lifecycle API (openDocument)" in item for item in scan_open_document_architecture(
        ROOT, source_overrides={LEAF: broken},
    ))


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_open_document_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "OPEN_DOCUMENT008 public adapter bypasses response validation" in scan_open_document_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_open_document_request("
    broken = "from typing import Any\n\ndef build_open_document_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "OPEN_DOCUMENT014 typed open_document surface contains Any: open_document leaf" in scan_open_document_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
