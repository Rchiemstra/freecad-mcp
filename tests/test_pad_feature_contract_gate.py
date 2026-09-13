"""Sensitivity checks for the pad_feature static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_pad_feature_contract import scan_pad_feature_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/pad_feature.py"
MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/pad_feature_mutation.py"
BRIDGE = "addon/FreeCADMCP/collaboration_api.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/pad_feature.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_pad_feature_architecture_gate_accepts_the_production_path() -> None:
    assert scan_pad_feature_architecture(ROOT) == []


@pytest.mark.parametrize(
    ("relative", "old", "broken", "expected"),
    [
        (
            LEAF,
            "            self.inspect,",
            "            self.apply,",
            "PAD_004 missing typed postcondition=inspect",
        ),
        (
            BRIDGE,
            "            return _unsupported(\n"
            '                "document must provide the native typed mutation contract"\n'
            "            )",
            "            callback(document)\n"
            '            return {"status": "Committed", "committed": True}',
            "PAD_006 postcondition path can reach non-native callback fallback",
        ),
        (
            BRIDGE,
            '        """Run a typed native mutation with apply and inspect on one document."""\n\n        document = self._resolve_admitted_document(document_name)',
            '        """Run a typed native mutation with apply and inspect on one document."""\n\n        document = self._resolve_admitted_document(document_name)\n        document = self._resolve_admitted_document(document_name)',
            "PAD_005 bridge must resolve the admitted document exactly once",
        ),
        (
            PUBLIC_ADAPTER,
            "result = parse_pad_feature_response(raw_result)",
            "result = raw_result",
            "PAD_008 public adapter bypasses response validation",
        ),
        (
            MUTATION,
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "    if state.postcondition_passed:\n        return True\n"
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "PAD_007 cached success escaped native rejection",
        ),
        (
            MUTATION,
            "if state.postcondition_passed and state.failure is None:",
            "if True:",
            "PAD_015 commit escaped without a successful postcondition",
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

    assert expected in scan_pad_feature_architecture(
        ROOT,
        source_overrides={relative: mutated},
    )


def test_gate_rejects_transaction_or_recompute_ownership_in_the_leaf() -> None:
    source = _read(LEAF)
    marker = '    """Create a Pad without recomputing or managing a transaction."""'
    assert source.count(marker) == 1
    mutated = source.replace(marker, marker + "\n\n    doc.recompute()")

    assert "PAD_001 leaf owns forbidden execution: recompute" in (
        scan_pad_feature_architecture(
            ROOT,
            source_overrides={LEAF: mutated},
        )
    )


def test_gate_rejects_any_on_the_pad_feature_specific_surface() -> None:
    source = _read(LEAF)
    old = 'def build_pad_feature_request(\n    doc_name: object,'
    broken = 'def build_pad_feature_request(\n    doc_name: Any,'
    assert source.count(old) == 1

    assert "PAD_014 typed PadFeature surface contains Any: PadFeature leaf" in (
        scan_pad_feature_architecture(
            ROOT,
            source_overrides={LEAF: source.replace(old, broken)},
        )
    )
