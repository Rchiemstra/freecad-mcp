"""Sensitivity checks for the ``activate_document`` static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_activate_document_contract import scan_activate_document_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/activate_document.py"
MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/activate_document_mutation.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/activate_document.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_activate_document_architecture_gate_accepts_the_production_path() -> None:
    assert scan_activate_document_architecture(ROOT) == []


@pytest.mark.parametrize(
    ("relative", "old", "broken", "expected"),
    [
        (
            LEAF,
            "            self.inspect,",
            "            self.apply,",
            "ACTIVATE_DOCUMENT004 missing typed postcondition=inspect",
        ),
        (
            PUBLIC_ADAPTER,
            "result = parse_activate_document_response(raw_result)",
            "result = raw_result",
            "ACTIVATE_DOCUMENT008 public adapter bypasses response validation",
        ),
        (
            MUTATION,
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "    if state.postcondition_passed:\n        return True\n"
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "ACTIVATE_DOCUMENT007 cached success escaped native rejection",
        ),
        (
            MUTATION,
            "if state.postcondition_passed and state.failure is None:",
            "if True:",
            "ACTIVATE_DOCUMENT015 commit escaped without a successful postcondition",
        ),
    ],
)
def test_gate_rejects_each_known_bad_variant(relative, old, broken, expected) -> None:
    source = _read(relative)
    assert source.count(old) == 1
    assert expected in scan_activate_document_architecture(ROOT, source_overrides={relative: source.replace(old, broken)})






def test_gate_rejects_recompute_ownership_in_the_leaf() -> None:
    source = _read(LEAF)
    marker = '    """Apply activate_document without recomputing or managing a transaction."""'
    assert source.count(marker) == 1
    mutated = source.replace(marker, marker + "\n\n    doc.recompute()")
    assert "ACTIVATE_DOCUMENT001 leaf owns forbidden execution: recompute" in scan_activate_document_architecture(
        ROOT, source_overrides={LEAF: mutated}
    )


def test_gate_rejects_any_on_the_typed_surface() -> None:
    source = _read(LEAF)
    old = 'def build_activate_document_request(doc_name: object)'
    broken = old.replace(": object", ": Any", 1)
    assert source.count(old) == 1
    assert "ACTIVATE_DOCUMENT014 typed surface contains Any: leaf" in scan_activate_document_architecture(
        ROOT, source_overrides={LEAF: source.replace(old, broken)}
    )
