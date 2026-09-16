"""Sensitivity checks for the ``get_dependency_graph`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_get_dependency_graph_contract import scan_get_dependency_graph_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/get_dependency_graph.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/get_dependency_graph.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_get_dependency_graph_architecture_gate_passes_the_production_path() -> None:
    assert scan_get_dependency_graph_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = source.replace(
        "    request = build_get_dependency_graph_request(doc_name, root)",
        "    run_get_dependency_graph_native_mutation(collaborators, \"\", lambda _d: None, lambda _d: None)\n    request = build_get_dependency_graph_request(doc_name, root)",
        1,
    )
    assert any("fake mutation pipeline" in item for item in scan_get_dependency_graph_architecture(
        ROOT, source_overrides={LEAF: broken},
    ))


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_get_dependency_graph_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "GET_DEPENDENCY_GRAPH008 public adapter bypasses response validation" in scan_get_dependency_graph_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_get_dependency_graph_request("
    broken = "from typing import Any\n\ndef build_get_dependency_graph_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "GET_DEPENDENCY_GRAPH014 typed get_dependency_graph surface contains Any: get_dependency_graph leaf" in scan_get_dependency_graph_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
