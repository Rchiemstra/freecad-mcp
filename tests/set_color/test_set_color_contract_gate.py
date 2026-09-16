"""Sensitivity checks for the ``set_color`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_set_color_contract import scan_set_color_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/set_color.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/set_color.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_set_color_architecture_gate_passes_the_production_path() -> None:
    assert scan_set_color_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = source.replace(
        "    request = build_set_color_request(doc_name, obj_name, r, g, b, transparency)",
        "    run_set_color_native_mutation(collaborators, \"\", lambda _d: None, lambda _d: None)\n    request = build_set_color_request(doc_name, obj_name, r, g, b, transparency)",
        1,
    )
    assert any(
        "commit_native_mutation" in item or "fake mutation pipeline" in item
        for item in scan_set_color_architecture(ROOT, source_overrides={LEAF: broken})
    )


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_set_color_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "SET_COLOR008 public adapter bypasses response validation" in scan_set_color_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_set_color_request("
    broken = "from typing import Any\n\ndef build_set_color_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "SET_COLOR014 typed set_color surface contains Any: set_color leaf" in scan_set_color_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
