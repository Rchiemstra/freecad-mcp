"""Sensitivity checks for the sketch_add_constraint static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_sketch_add_constraint_contract import scan_sketch_add_constraint_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/sketch_add_constraint.py"
MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/sketch_add_constraint_mutation.py"
BRIDGE = "addon/FreeCADMCP/collaboration_api.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/sketch_add_constraint.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_sketch_add_constraint_architecture_gate_accepts_the_production_path() -> None:
    assert scan_sketch_add_constraint_architecture(ROOT) == []


@pytest.mark.parametrize(
    ("relative", "old", "broken", "expected"),
    [
        (
            LEAF,
            "            self.inspect,",
            "            self.apply,",
            "SKET004 missing typed postcondition=inspect",
        ),
        (
            BRIDGE,
            "            return _unsupported(\n"
            '                "document must provide the native typed mutation contract"\n'
            "            )",
            "            callback(document)\n"
            '            return {"status": "Committed", "committed": True}',
            "SKET006 postcondition path can reach non-native callback fallback",
        ),
        (
            BRIDGE,
            '        """Run a typed native mutation with apply and inspect on one document."""\n\n        document = self._resolve_admitted_document(document_name)',
            '        """Run a typed native mutation with apply and inspect on one document."""\n\n        document = self._resolve_admitted_document(document_name)\n        document = self._resolve_admitted_document(document_name)',
            "SKET005 bridge must resolve the admitted document exactly once",
        ),
        (
            PUBLIC_ADAPTER,
            "result = parse_sketch_add_constraint_response(raw_result)",
            "result = raw_result",
            "SKET008 public adapter bypasses response validation",
        ),
        (
            MUTATION,
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "    if state.postcondition_passed:\n        return True\n"
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "SKET007 cached success escaped native rejection",
        ),
        (
            MUTATION,
            "if state.postcondition_passed and state.failure is None:",
            "if True:",
            "SKET015 commit escaped without a successful postcondition",
        ),
    ],
    ids=(
        "inspection-before-final-recompute",
        "non-native-fallback",
        "independent-document-resolution",
        "absence-of-false-means-success",
        "cached-success-after-native-rejection",
        "missing-postcondition",
    ),
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

    assert expected in scan_sketch_add_constraint_architecture(
        ROOT,
        source_overrides={relative: mutated},
    )


def test_gate_rejects_transaction_or_recompute_ownership_in_the_leaf() -> None:
    source = _read(LEAF)
    marker = '    """Add sketch constraints without recomputing or managing a transaction."""'
    assert source.count(marker) == 1
    mutated = source.replace(marker, marker + "\n\n    doc.recompute()")

    assert "SKET001 leaf owns forbidden execution: recompute" in (
        scan_sketch_add_constraint_architecture(
            ROOT,
            source_overrides={LEAF: mutated},
        )
    )


def test_gate_rejects_any_on_the_sketch_add_constraint_specific_surface() -> None:
    source = _read(LEAF)
    old = 'def build_sketch_add_constraint_request(\n    doc_name: object, sketch_name: object, constraints: object'
    broken = 'def build_sketch_add_constraint_request(\n    doc_name: Any, sketch_name: object, constraints: object'
    assert source.count(old) == 1

    assert "SKET014 typed SketchAddConstraint surface contains Any: SketchAddConstraint leaf" in (
        scan_sketch_add_constraint_architecture(
            ROOT,
            source_overrides={LEAF: source.replace(old, broken)},
        )
    )
