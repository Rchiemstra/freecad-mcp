"""Sensitivity checks for the ``get_document_tree`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_get_document_tree_contract import scan_get_document_tree_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/get_document_tree.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/get_document_tree.py"
REQUEST_MARKER = (
    "    request = build_get_document_tree_request(\n"
    "        doc_name, root_filter, max_depth, include, include_properties, selected_nodes\n"
    "    )"
)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_get_document_tree_architecture_gate_passes_the_production_path() -> None:
    assert scan_get_document_tree_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = source.replace(
        REQUEST_MARKER,
        "    run_get_document_tree_native_mutation(collaborators, \"\", lambda _d: None, lambda _d: None)\n"
        + REQUEST_MARKER,
        1,
    )
    assert any("fake mutation pipeline" in item for item in scan_get_document_tree_architecture(
        ROOT, source_overrides={LEAF: broken},
    ))


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_get_document_tree_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "GET_DOCUMENT_TREE008 public adapter bypasses response validation" in scan_get_document_tree_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_get_document_tree_request("
    broken = "from typing import Any\n\ndef build_get_document_tree_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "GET_DOCUMENT_TREE014 typed get_document_tree surface contains Any: get_document_tree leaf" in scan_get_document_tree_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
