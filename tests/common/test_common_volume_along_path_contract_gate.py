"""Sensitivity checks for the ``common_volume_along_path`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_common_volume_along_path_contract import scan_common_volume_along_path_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/common_volume_along_path.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/common_volume_along_path.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_common_volume_along_path_architecture_gate_passes_the_production_path() -> None:
    assert scan_common_volume_along_path_architecture(ROOT) == []


def test_gate_rejects_legacy_policy_sins_via_source_override() -> None:
    source = _read(LEAF)
    broken = source.replace(
        "    request = build_common_volume_along_path_request(",
        "    run_common_volume_along_path_native_mutation(collaborators, \"\", lambda _d: None, lambda _d: None)\n    request = build_common_volume_along_path_request(",
        1,
    )
    assert any("fake mutation pipeline" in item for item in scan_common_volume_along_path_architecture(
        ROOT, source_overrides={LEAF: broken},
    ))


def test_gate_rejects_adapter_bypass() -> None:
    source = _read(PUBLIC_ADAPTER)
    old = "result = parse_common_volume_along_path_response(raw_result)"
    broken = "result = raw_result"
    assert source.count(old) == 1
    assert "COMMON_VOLUME_ALONG_PATH008 public adapter bypasses response validation" in scan_common_volume_along_path_architecture(
        ROOT,
        source_overrides={PUBLIC_ADAPTER: source.replace(old, broken)},
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_common_volume_along_path_request("
    broken = "from typing import Any\n\ndef build_common_volume_along_path_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "COMMON_VOLUME_ALONG_PATH014 typed common_volume_along_path surface contains Any: common_volume_along_path leaf" in scan_common_volume_along_path_architecture(
        ROOT,
        source_overrides={LEAF: source.replace(old, broken, 1)},
    )
