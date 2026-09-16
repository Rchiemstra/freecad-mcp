"""Sensitivity checks for the ``chamfer_feature`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.scan_typed_feature_contract import scan_feature_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/chamfer_feature.py"
MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/chamfer_feature_mutation.py"
BRIDGE = "addon/FreeCADMCP/collaboration_api.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/chamfer_feature.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_chamfer_feature_architecture_gate_accepts_the_production_path() -> None:
    assert scan_feature_architecture(ROOT, "chamfer_feature") == []


@pytest.mark.parametrize(
    ("relative", "old", "broken", "expected"),
    [
        (
            LEAF,
            "            self.inspect,",
            "            self.apply,",
            "CHAMFER_FEATURE004 missing typed postcondition=inspect",
        ),
        (
            PUBLIC_ADAPTER,
            "result = parse_chamfer_feature_response(raw_result)",
            "result = raw_result",
            "CHAMFER_FEATURE008 public adapter bypasses response validation",
        ),
        (
            MUTATION,
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "    if state.postcondition_passed:\n        return True\n"
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "CHAMFER_FEATURE007 cached success escaped native rejection",
        ),
        (
            MUTATION,
            "if state.postcondition_passed and state.failure is None:",
            "if True:",
            "CHAMFER_FEATURE015 commit escaped without a successful postcondition",
        ),
    ],
)
def test_gate_rejects_each_known_bad_variant_for_the_intended_reason(
    relative: str,
    old: str,
    broken: str,
    expected: str,
) -> None:
    source = _read(relative)
    assert source.count(old) == 1
    mutated = source.replace(old, broken)
    assert expected in scan_feature_architecture(
        ROOT,
        "chamfer_feature",
        source_overrides={relative: mutated},
    )


def test_gate_rejects_transaction_or_recompute_ownership_in_the_leaf() -> None:
    source = _read(LEAF)
    marker = '    """Apply the mutation without recomputing or managing a transaction."""'
    assert source.count(marker) == 1
    mutated = source.replace(marker, marker + "\n\n    doc.recompute()")
    assert "CHAMFER_FEATURE001 leaf owns forbidden execution: recompute" in (
        scan_feature_architecture(
            ROOT,
            "chamfer_feature",
            source_overrides={LEAF: mutated},
        )
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = "def build_chamfer_feature_request("
    broken = "from typing import Any\n\ndef build_chamfer_feature_request(\n    unused: Any,"
    assert source.count(old) == 1
    assert "CHAMFER_FEATURE014 typed chamfer_feature surface contains Any: chamfer_feature leaf" in (
        scan_feature_architecture(
            ROOT,
            "chamfer_feature",
            source_overrides={LEAF: source.replace(old, broken, 1)},
        )
    )
