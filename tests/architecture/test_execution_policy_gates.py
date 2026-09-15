"""Cross-policy architecture gate coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci.check_body_create_contract import scan_body_create_architecture
from ci.scan_execution_policy_gates import policy_for_op, scan_op_architecture
from ci.scan_typed_feature_contract import scan_feature_architecture

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
BOOLEAN_LEAF = "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/boolean_union.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_boolean_union_mutation_architecture_passes() -> None:
    assert scan_feature_architecture(ROOT, "boolean_union") == []
    assert scan_op_architecture(ROOT, "boolean_union") == []


def test_body_create_golden_mutation_architecture_passes() -> None:
    assert scan_body_create_architecture(ROOT) == []
    assert scan_op_architecture(ROOT, "body_create") == []


def test_mutation_gate_rejects_writes_in_inspect_not_apply() -> None:
    source = _read(BOOLEAN_LEAF)
    marker = "        self.inspected = read_boolean_union_result(doc, self.created)"
    assert source.count(marker) == 1
    mutated = source.replace(
        marker,
        '        doc.addObject("Part::Feature", "x")\n        self.inspected = read_boolean_union_result(doc, self.created)',
    )
    violations = scan_feature_architecture(
        ROOT,
        "boolean_union",
        source_overrides={BOOLEAN_LEAF: mutated},
    )
    assert any("BOOLEAN_UNION019 inspect path performs writes: addObject" in item for item in violations)


def test_mutation_gate_rejects_close_document_in_run_boolean_union() -> None:
    source = _read(BOOLEAN_LEAF)
    marker = "    return _BooleanUnionExecution(collaborators, request).run()"
    assert source.count(marker) == 1
    mutated = source.replace(
        marker,
        '    collaborators.closeDocument("x")\n    return _BooleanUnionExecution(collaborators, request).run()',
    )
    violations = scan_feature_architecture(
        ROOT,
        "boolean_union",
        source_overrides={BOOLEAN_LEAF: mutated},
    )
    assert any("BOOLEAN_UNION018 run_boolean_union owns forbidden CAD side effects" in item for item in violations)


def test_close_document_production_passes_lifecycle_policy() -> None:
    assert scan_op_architecture(ROOT, "close_document") == []


def test_bounding_box_production_passes_query_policy() -> None:
    assert scan_op_architecture(ROOT, "bounding_box") == []


def test_undo_and_redo_production_pass_history_policy() -> None:
    assert scan_op_architecture(ROOT, "undo") == []
    assert scan_op_architecture(ROOT, "redo") == []


def test_export_step_production_passes_external_effect_policy() -> None:
    assert scan_op_architecture(ROOT, "export_step") == []


def test_set_color_production_passes_gui_global_policy() -> None:
    assert scan_op_architecture(ROOT, "set_color") == []


def test_gui_synthetic_committed_and_transaction_fail() -> None:
    synthetic = '''
def run_set_color(collaborators, object_name, color):
    collaborators.commit_native_mutation("Doc", lambda doc: None, lambda doc: None)
    return {"success": True, "committed": True, "outcome": "committed"}

def set_color_operation(client, object_name, color):
    raw = client.set_color(object_name, color)
    return parse_set_color_response(raw)

def parse_set_color_response(raw):
    return raw
'''
    violations = scan_op_architecture(
        ROOT,
        "set_color",
        source_overrides={
            "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/set_color.py": synthetic,
            "src/freecad_mcp/operations/parametric_ops/set_color.py": synthetic,
            "addon/FreeCADMCP/_shared/protocol/set_color_contract.py": (
                'outcome: Literal["committed"]\ncommitted: Literal[True]\n'
            ),
            "src/freecad_mcp/_shared/protocol/set_color_contract.py": (
                'outcome: Literal["committed"]\ncommitted: Literal[True]\n'
            ),
        },
    )
    assert any(item.startswith("GUI set_color") for item in violations)


def test_dispatcher_uses_registry_policy_for_bounding_box() -> None:
    assert policy_for_op(ROOT, "bounding_box") == "document_query"
    violations = scan_op_architecture(ROOT, "bounding_box")
    assert violations == []
    assert not any("must use exactly one typed mutation call" in item for item in violations)


def test_sketch_offset_production_passes_mutation_policy() -> None:
    assert scan_op_architecture(ROOT, "sketch_offset") == []


def test_measure_distance_production_passes_query_policy() -> None:
    assert policy_for_op(ROOT, "measure_distance") == "document_query"
    assert scan_op_architecture(ROOT, "measure_distance") == []


def test_get_document_tree_production_passes_query_policy() -> None:
    assert policy_for_op(ROOT, "get_document_tree") == "document_query"
    assert scan_op_architecture(ROOT, "get_document_tree") == []


def test_diagnose_pocket_production_passes_query_policy() -> None:
    assert policy_for_op(ROOT, "diagnose_pocket") == "document_query"
    assert scan_op_architecture(ROOT, "diagnose_pocket") == []
