"""Sensitivity checks for the ``match_subshape`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_match_subshape_contract import scan_match_subshape_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/match_subshape.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/match_subshape.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_match_subshape_architecture_gate_passes_the_production_path() -> None:
    assert scan_match_subshape_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = source.replace(
        "    request = build_match_subshape_request(doc_name, source_object, source_subshape, target_object, limit, tolerance)",
        "    run_match_subshape_native_mutation(collaborators, \"\", lambda _d: None, lambda _d: None)\n    request = build_match_subshape_request(doc_name, source_object, source_subshape, target_object, limit, tolerance)",
        1,
    )
    assert any("fake mutation pipeline" in item for item in scan_match_subshape_architecture(
        ROOT, source_overrides={LEAF: broken},
    ))


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_match_subshape_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "MATCH_SUBSHAPE008 public adapter bypasses response validation" in scan_match_subshape_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_match_subshape_request("
    broken = "from typing import Any\n\ndef build_match_subshape_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "MATCH_SUBSHAPE014 typed match_subshape surface contains Any: match_subshape leaf" in scan_match_subshape_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
