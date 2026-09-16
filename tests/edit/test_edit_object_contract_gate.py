"""Sensitivity checks for the ``edit_object`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_edit_object_contract import scan_edit_object_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/edit_object.py"
MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/edit_object_mutation.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/edit_object.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_edit_object_architecture_gate_accepts_the_production_path() -> None:
    assert scan_edit_object_architecture(ROOT) == []


@pytest.mark.parametrize(
    ("relative", "old", "broken", "expected"),
    [
        (
            LEAF,
            "            self.inspect,",
            "            self.apply,",
            "EDIT_OBJECT004 missing typed postcondition=inspect",
        ),
        (
            PUBLIC_ADAPTER,
            "result = parse_edit_object_response(raw_result)",
            "result = raw_result",
            "EDIT_OBJECT008 public adapter bypasses response validation",
        ),
        (
            MUTATION,
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "    if state.postcondition_passed:\n        return True\n"
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "EDIT_OBJECT007 cached success escaped native rejection",
        ),
        (
            MUTATION,
            "if state.postcondition_passed and state.failure is None:",
            "if True:",
            "EDIT_OBJECT015 commit escaped without a successful postcondition",
        ),
    ],
)
def test_gate_rejects_each_known_bad_variant(relative, old, broken, expected) -> None:
    source = _read(relative)
    assert source.count(old) == 1
    assert expected in scan_edit_object_architecture(ROOT, source_overrides={relative: source.replace(old, broken)})






def test_gate_rejects_recompute_ownership_in_the_leaf() -> None:
    source = _read(LEAF)
    marker = '    """Edit an object without recomputing or managing a transaction."""'
    assert source.count(marker) == 1
    mutated = source.replace(marker, marker + "\n\n    doc.recompute()")
    assert "EDIT_OBJECT001 leaf owns forbidden execution: recompute" in scan_edit_object_architecture(
        ROOT, source_overrides={LEAF: mutated}
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = 'def build_edit_object_request(\n    doc_name: object, obj_name: object, properties: object'
    broken = old.replace(": object", ": Any", 1)
    assert source.count(old) == 1
    assert "EDIT_OBJECT014 typed edit_object surface contains Any: edit_object leaf" in scan_edit_object_architecture(
        ROOT, source_overrides={LEAF: source.replace(old, broken)}
    )
