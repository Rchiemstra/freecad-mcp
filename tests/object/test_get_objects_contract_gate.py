"""Sensitivity checks for the ``get_objects`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_get_objects_contract import scan_get_objects_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/get_objects.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/core_ops/object_ops.py"
REQUEST_MARKER = (
    "    request = build_get_objects_request(\n"
    "        doc_name,\n"
    "        fields,\n"
    "        include_properties,\n"
    "        include_shape,\n"
    "        include_view,\n"
    "        page_size,\n"
    "        cursor,\n"
    "    )"
)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_get_objects_architecture_gate_passes_the_production_path() -> None:
    assert scan_get_objects_architecture(ROOT) == []


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_get_objects_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    violations = scan_get_objects_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )
    assert "GET_OBJECTS008 public adapter bypasses response validation" in violations


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_get_objects_request("
    broken = (
        "from typing import Any\n\n"
        "def build_get_objects_request(\n"
        "    unused: Any,"
    )
    assert source.count(old) == 1
    violations = scan_get_objects_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
    message = "GET_OBJECTS014 typed get_objects surface contains Any: get_objects leaf"
    assert message in violations
