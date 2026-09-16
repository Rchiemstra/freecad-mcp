"""Sensitivity checks for the ``validate_geometry`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_validate_geometry_contract import scan_validate_geometry_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/validate_geometry.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/validate_geometry.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_validate_geometry_architecture_gate_passes_the_production_path() -> None:
    assert scan_validate_geometry_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = source.replace(
        "    request = build_validate_geometry_request(doc_name, obj_name)",
        "    run_validate_geometry_native_mutation(collaborators, \"\", lambda _d: None, lambda _d: None)\n    request = build_validate_geometry_request(doc_name, obj_name)",
        1,
    )
    assert any("fake mutation pipeline" in item for item in scan_validate_geometry_architecture(
        ROOT, source_overrides={LEAF: broken},
    ))


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_validate_geometry_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "VALIDATE_GEOMETRY008 public adapter bypasses response validation" in scan_validate_geometry_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_validate_geometry_request("
    broken = "from typing import Any\n\ndef build_validate_geometry_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "VALIDATE_GEOMETRY014 typed validate_geometry surface contains Any: validate_geometry leaf" in scan_validate_geometry_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
