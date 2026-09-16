"""Sensitivity checks for the Body static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_body_create_contract import scan_body_create_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
BODY_LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/body_create.py"
MUTATION = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/body_mutation.py"
BRIDGE = "addon/FreeCADMCP/collaboration_api.py"
PUBLIC_ADAPTER = "src/freecad_mcp/operations/parametric_ops/body_ops.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_body_create_architecture_gate_accepts_the_production_path() -> None:
    assert scan_body_create_architecture(ROOT) == []


@pytest.mark.parametrize(
    ("relative", "old", "broken", "expected"),
    [
        (
            BODY_LEAF,
            "            self.inspect,",
            "            self.apply,",
            "BODY004 missing typed postcondition=inspect",
        ),
        (
            BRIDGE,
            "            return _unsupported(\n"
            '                "document must provide the native Body mutation contract"\n'
            "            )",
            "            callback(document)\n"
            '            return {"status": "Committed", "committed": True}',
            "BODY006 postcondition path can reach non-native callback fallback",
        ),
        (
            BRIDGE,
            '        """Run Body creation only when the exact native contract is present."""\n\n        document = self._resolve_admitted_document(document_name)',
            '        """Run Body creation only when the exact native contract is present."""\n\n        document = self._resolve_admitted_document(document_name)\n        document = self._resolve_admitted_document(document_name)',
            "BODY005 bridge must resolve the admitted document exactly once",
        ),
        (
            PUBLIC_ADAPTER,
            "result = parse_body_create_response(raw_result)",
            "result = raw_result",
            "BODY008 public adapter bypasses response validation",
        ),
        (
            MUTATION,
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "    if state.postcondition_passed:\n        return True\n"
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "BODY007 cached success escaped native rejection",
        ),
        (
            MUTATION,
            "if state.postcondition_passed and state.failure is None:",
            "if True:",
            "BODY015 commit escaped without a successful postcondition",
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

    assert expected in scan_body_create_architecture(
        ROOT,
        source_overrides={relative: mutated},
    )


def test_gate_rejects_transaction_or_recompute_ownership_in_the_leaf() -> None:
    source = _read(BODY_LEAF)
    marker = '    """Create a Body without recomputing or managing a transaction."""'
    assert source.count(marker) == 1
    mutated = source.replace(marker, marker + "\n\n    doc.recompute()")

    assert "BODY001 leaf owns forbidden execution: recompute" in (
        scan_body_create_architecture(
            ROOT,
            source_overrides={BODY_LEAF: mutated},
        )
    )


def test_gate_rejects_any_on_the_body_specific_surface() -> None:
    source = _read(BODY_LEAF)
    old = "def build_body_create_request(\n    doc_name: object, body_name: object"
    broken = "def build_body_create_request(\n    doc_name: Any, body_name: object"
    assert source.count(old) == 1

    assert "BODY014 typed Body surface contains Any: Body leaf" in (
        scan_body_create_architecture(
            ROOT,
            source_overrides={BODY_LEAF: source.replace(old, broken)},
        )
    )
