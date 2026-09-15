"""Sensitivity checks for the ``create_object`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_create_object_contract import scan_create_object_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/create_object.py"
MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/create_object_mutation.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/create_object.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_create_object_architecture_gate_accepts_the_production_path() -> None:
    assert scan_create_object_architecture(ROOT) == []


@pytest.mark.parametrize(
    ("relative", "old", "broken", "expected"),
    [
        (
            LEAF,
            "            self.inspect,",
            "            self.apply,",
            "CREATE_OBJECT004 missing typed postcondition=inspect",
        ),
        (
            PUBLIC_ADAPTER,
            "result = parse_create_object_response(raw_result)",
            "result = raw_result",
            "CREATE_OBJECT008 public adapter bypasses response validation",
        ),
        (
            MUTATION,
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "    if state.postcondition_passed:\n        return True\n"
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "CREATE_OBJECT007 cached success escaped native rejection",
        ),
        (
            MUTATION,
            "if state.postcondition_passed and state.failure is None:",
            "if True:",
            "CREATE_OBJECT015 commit escaped without a successful postcondition",
        ),
    ],
)
def test_gate_rejects_each_known_bad_variant(relative, old, broken, expected) -> None:
    source = _read(relative)
    assert source.count(old) == 1
    assert expected in scan_create_object_architecture(ROOT, source_overrides={relative: source.replace(old, broken)})






def test_gate_rejects_recompute_ownership_in_the_leaf() -> None:
    source = _read(LEAF)
    marker = '    """Create an object without recomputing or managing a transaction."""'
    assert source.count(marker) == 1
    mutated = source.replace(marker, marker + "\n\n    doc.recompute()")
    assert "CREATE_OBJECT001 leaf owns forbidden execution: recompute" in scan_create_object_architecture(
        ROOT, source_overrides={LEAF: mutated}
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = 'def build_create_object_request(\n    doc_name: object, obj_data: object'
    broken = old.replace(": object", ": Any", 1)
    assert source.count(old) == 1
    assert "CREATE_OBJECT014 typed create_object surface contains Any: create_object leaf" in scan_create_object_architecture(
        ROOT, source_overrides={LEAF: source.replace(old, broken)}
    )
