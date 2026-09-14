"""Sensitivity checks for the ``undo`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_undo_contract import scan_undo_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/undo.py"
MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/undo_mutation.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/undo.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_undo_architecture_gate_accepts_the_production_path() -> None:
    assert scan_undo_architecture(ROOT) == []


@pytest.mark.parametrize(
    ("relative", "old", "broken", "expected"),
    [
        (
            LEAF,
            "            self.inspect,",
            "            self.apply,",
            "UNDO004 missing typed postcondition=inspect",
        ),
        (
            PUBLIC_ADAPTER,
            "result = parse_undo_response(raw_result)",
            "result = raw_result",
            "UNDO008 public adapter bypasses response validation",
        ),
        (
            MUTATION,
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "    if state.postcondition_passed:\n        return True\n"
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "UNDO007 cached success escaped native rejection",
        ),
        (
            MUTATION,
            "if state.postcondition_passed and state.failure is None:",
            "if True:",
            "UNDO015 commit escaped without a successful postcondition",
        ),
    ],
)
def test_gate_rejects_each_known_bad_variant(relative, old, broken, expected) -> None:
    source = _read(relative)
    assert source.count(old) == 1
    assert expected in scan_undo_architecture(ROOT, source_overrides={relative: source.replace(old, broken)})






def test_gate_rejects_recompute_ownership_in_the_leaf() -> None:
    source = _read(LEAF)
    marker = '    """Record document identity; undo runs after native commit."""'
    assert source.count(marker) == 1
    mutated = source.replace(marker, marker + "\n\n    doc.recompute()")
    assert "UNDO001 leaf owns forbidden execution: recompute" in scan_undo_architecture(
        ROOT, source_overrides={LEAF: mutated}
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = 'def build_undo_request(doc_name: object)'
    broken = old.replace(": object", ": Any", 1)
    assert source.count(old) == 1
    assert "UNDO014 typed surface contains Any: leaf" in scan_undo_architecture(
        ROOT, source_overrides={LEAF: source.replace(old, broken)}
    )
