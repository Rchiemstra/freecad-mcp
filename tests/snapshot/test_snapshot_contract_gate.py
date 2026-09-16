"""Sensitivity checks for the ``snapshot`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_snapshot_contract import scan_snapshot_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/snapshot.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/snapshot.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_snapshot_architecture_gate_passes_the_production_path() -> None:
    assert scan_snapshot_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = source.replace(
        "    request = build_snapshot_request(doc_name)",
        "    run_snapshot_native_mutation(collaborators, \"\", lambda _d: None, lambda _d: None)\n    request = build_snapshot_request(doc_name)",
        1,
    )
    assert any("fake mutation pipeline" in item for item in scan_snapshot_architecture(
        ROOT, source_overrides={LEAF: broken},
    ))


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_snapshot_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "SNAPSHOT008 public adapter bypasses response validation" in scan_snapshot_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_snapshot_request("
    broken = "from typing import Any\n\ndef build_snapshot_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "SNAPSHOT014 typed snapshot surface contains Any: snapshot leaf" in scan_snapshot_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
