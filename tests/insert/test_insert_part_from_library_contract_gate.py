"""Sensitivity checks for the ``insert_part_from_library`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_insert_part_from_library_contract import scan_insert_part_from_library_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/insert_part_from_library.py"
MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/insert_part_from_library_mutation.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/insert_part_from_library.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_insert_part_from_library_architecture_gate_accepts_the_production_path() -> None:
    assert scan_insert_part_from_library_architecture(ROOT) == []


@pytest.mark.parametrize(
    ("relative", "old", "broken", "expected"),
    [
        (
            LEAF,
            "            self.inspect,",
            "            self.apply,",
            "INSERT_PART_FROM_LIBRARY004 missing typed postcondition=inspect",
        ),
        (
            PUBLIC_ADAPTER,
            "result = parse_insert_part_from_library_response(raw_result)",
            "result = raw_result",
            "INSERT_PART_FROM_LIBRARY008 public adapter bypasses response validation",
        ),
        (
            MUTATION,
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "    if state.postcondition_passed:\n        return True\n"
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "INSERT_PART_FROM_LIBRARY007 cached success escaped native rejection",
        ),
        (
            MUTATION,
            "if state.postcondition_passed and state.failure is None:",
            "if True:",
            "INSERT_PART_FROM_LIBRARY015 commit escaped without a successful postcondition",
        ),
    ],
)
def test_gate_rejects_each_known_bad_variant(relative, old, broken, expected) -> None:
    source = _read(relative)
    assert source.count(old) == 1
    assert expected in scan_insert_part_from_library_architecture(ROOT, source_overrides={relative: source.replace(old, broken)})






def test_gate_rejects_recompute_ownership_in_the_leaf() -> None:
    source = _read(LEAF)
    marker = '    """Insert a library part without recomputing or managing a transaction."""'
    assert source.count(marker) == 1
    mutated = source.replace(marker, marker + "\n\n    doc.recompute()")
    assert "INSERT_PART_FROM_LIBRARY001 leaf owns forbidden execution: recompute" in scan_insert_part_from_library_architecture(
        ROOT, source_overrides={LEAF: mutated}
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = 'def build_insert_part_from_library_request(\n    doc_name: object, relative_path: object'
    broken = old.replace(": object", ": Any", 1)
    assert source.count(old) == 1
    assert "INSERT_PART_FROM_LIBRARY014 typed insert_part_from_library surface contains Any: insert_part_from_library leaf" in scan_insert_part_from_library_architecture(
        ROOT, source_overrides={LEAF: source.replace(old, broken)}
    )
