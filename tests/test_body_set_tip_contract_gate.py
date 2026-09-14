"""Sensitivity checks for the Body Tip static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_body_set_tip_contract import scan_body_set_tip_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TIP_LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/body_set_tip.py"
MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/body_set_tip_mutation.py"
BRIDGE = "addon/FreeCADMCP/collaboration_api.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/body_set_tip.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_body_set_tip_architecture_gate_accepts_the_production_path() -> None:
    assert scan_body_set_tip_architecture(ROOT) == []


@pytest.mark.parametrize(
    ("relative", "old", "broken", "expected"),
    [
        (
            TIP_LEAF,
            "            self.inspect,",
            "            self.apply,",
            "TIP004 missing typed postcondition=inspect",
        ),
        (
            BRIDGE,
            "            return _unsupported(\n"
            '                "document must provide the native typed mutation contract"\n'
            "            )",
            "            callback(document)\n"
            '            return {"status": "Committed", "committed": True}',
            "TIP006 postcondition path can reach non-native callback fallback",
        ),
        (
            BRIDGE,
            '        """Run a typed native mutation with apply and inspect on one document."""\n\n        document = self._resolve_admitted_document(document_name)',
            '        """Run a typed native mutation with apply and inspect on one document."""\n\n        document = self._resolve_admitted_document(document_name)\n        document = self._resolve_admitted_document(document_name)',
            "TIP005 bridge must resolve the admitted document exactly once",
        ),
        (
            PUBLIC_ADAPTER,
            "result = parse_body_set_tip_response(raw_result)",
            "result = raw_result",
            "TIP008 public adapter bypasses response validation",
        ),
        (
            MUTATION,
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "    if state.postcondition_passed:\n        return True\n"
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "TIP007 cached success escaped native rejection",
        ),
        (
            MUTATION,
            "if state.postcondition_passed and state.failure is None:",
            "if True:",
            "TIP015 commit escaped without a successful postcondition",
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

    assert expected in scan_body_set_tip_architecture(
        ROOT,
        source_overrides={relative: mutated},
    )


def test_gate_rejects_transaction_or_recompute_ownership_in_the_leaf() -> None:
    source = _read(TIP_LEAF)
    marker = '    """Assign Body.Tip without recomputing or managing a transaction."""'
    assert source.count(marker) == 1
    mutated = source.replace(marker, marker + "\n\n    doc.recompute()")

    assert "TIP001 leaf owns forbidden execution: recompute" in (
        scan_body_set_tip_architecture(
            ROOT,
            source_overrides={TIP_LEAF: mutated},
        )
    )


def test_gate_rejects_any_on_the_tip_specific_surface() -> None:
    source = _read(TIP_LEAF)
    old = (
        "def build_body_set_tip_request(\n"
        "    doc_name: object, body_name: object, feature_name: object"
    )
    broken = (
        "def build_body_set_tip_request(\n"
        "    doc_name: Any, body_name: object, feature_name: object"
    )
    assert source.count(old) == 1

    assert "TIP014 typed Tip surface contains Any: Tip leaf" in (
        scan_body_set_tip_architecture(
            ROOT,
            source_overrides={TIP_LEAF: source.replace(old, broken)},
        )
    )


def test_gate_rejects_a_per_op_commit_method() -> None:
    source = _read(BRIDGE)
    broken = source + "\n    def commit_body_set_tip_mutation(self, document_name, callback, postcondition):\n        return None\n"
    assert "TIP016 per-op commit_body_set_tip_mutation is forbidden" in (
        scan_body_set_tip_architecture(
            ROOT,
            source_overrides={BRIDGE: broken},
        )
    )
