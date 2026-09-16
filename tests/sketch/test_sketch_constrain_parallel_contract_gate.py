"""Sensitivity checks for the sketch_constrain_parallel static and architecture gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.typed_sketch_contract import scan_sketch_op_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LEAF = 'addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/sketch_constrain_parallel.py'
MUTATION = 'addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/sketch_constrain_parallel_mutation.py'
BRIDGE = "addon/FreeCADMCP/collaboration_api.py"
PUBLIC_ADAPTER = 'src/freecad_mcp/operations/parametric_ops/sketch_constrain_parallel.py'


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_sketch_constrain_parallel_architecture_gate_accepts_the_production_path() -> None:
    assert scan_sketch_op_architecture(ROOT, "sketch_constrain_parallel") == []


@pytest.mark.parametrize(
    ("relative", "old", "broken", "expected"),
    [
        (
            LEAF,
            "            self.inspect,",
            "            self.apply,",
            "SKETCH_CONSTRAIN_PARALLEL004 missing typed postcondition=inspect",
        ),
        (
            BRIDGE,
            "            return _unsupported(\n"
            '                "document must provide the native typed mutation contract"\n'
            "            )",
            "            callback(document)\n"
            '            return {"status": "Committed", "committed": True}',
            "SKETCH_CONSTRAIN_PARALLEL006 postcondition path can reach non-native callback fallback",
        ),
        (
            PUBLIC_ADAPTER,
            "result = parse_sketch_constrain_parallel_response(raw_result)",
            "result = raw_result",
            "SKETCH_CONSTRAIN_PARALLEL008 public adapter bypasses response validation",
        ),
        (
            MUTATION,
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "    if state.postcondition_passed:\n        return True\n"
            "    if committed is not False or status not in _REJECTED_STATUSES:",
            "SKETCH_CONSTRAIN_PARALLEL007 cached success escaped native rejection",
        ),
        (
            MUTATION,
            "if state.postcondition_passed and state.failure is None:",
            "if True:",
            "SKETCH_CONSTRAIN_PARALLEL015 commit escaped without a successful postcondition",
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
    assert expected in scan_sketch_op_architecture(
        ROOT,
        "sketch_constrain_parallel",
        source_overrides={relative: mutated},
    )


def test_gate_rejects_transaction_or_recompute_ownership_in_the_leaf() -> None:
    source = _read(LEAF)
    marker = '    """Mutate the sketch without recomputing or managing a transaction."""'
    assert source.count(marker) == 1
    mutated = source.replace(marker, marker + "\n\n    doc.recompute()")
    assert "SKETCH_CONSTRAIN_PARALLEL001 leaf owns forbidden execution: recompute" in (
        scan_sketch_op_architecture(ROOT, "sketch_constrain_parallel", source_overrides={LEAF: mutated})
    )


def test_gate_rejects_any_on_the_op_specific_surface() -> None:
    source = _read(LEAF)
    old = "collaborators: SketchConstrainParallelCollaborators"
    broken = "collaborators: Any"
    assert old in source
    assert "SKETCH_CONSTRAIN_PARALLEL014 typed sketch_constrain_parallel surface contains Any: sketch_constrain_parallel leaf" in (
        scan_sketch_op_architecture(
            ROOT,
            "sketch_constrain_parallel",
            source_overrides={LEAF: source.replace(old, broken, 1)},
        )
    )
