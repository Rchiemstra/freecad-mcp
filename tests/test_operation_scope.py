"""Lease-scope contracts for generated operation wrappers.

These tests deliberately inspect the operation source as well as the options
produced by the shared helpers.  A newly added generated wrapper must declare
its live document explicitly; relying on ``ActiveDocument`` would bypass the
per-document lease boundary.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from freecad_mcp.operations.core import _run_code
from freecad_mcp.operations.p7_assembly import _run_json_code


OPERATIONS_ROOT = Path(__file__).parents[1] / "src" / "freecad_mcp" / "operations"


def _generated_calls() -> dict[tuple[str, str], list[ast.Call]]:
    calls: dict[tuple[str, str], list[ast.Call]] = {}
    for path in OPERATIONS_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for function in (node for node in tree.body if isinstance(node, ast.FunctionDef)):
            found = [
                node
                for node in ast.walk(function)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"_run_code", "_run_json_code"}
            ]
            if found:
                calls[(path.name, function.name)] = found
    return calls


def _keywords(call: ast.Call) -> dict[str, ast.expr]:
    return {keyword.arg: keyword.value for keyword in call.keywords if keyword.arg}


def _literal_true(expr: ast.expr | None) -> bool:
    return isinstance(expr, ast.Constant) and expr.value is True


def _literal(expr: ast.expr | None) -> object:
    return expr.value if isinstance(expr, ast.Constant) else None


def test_every_generated_operation_declares_its_document_scope() -> None:
    missing: list[str] = []
    wrong: list[str] = []
    for (filename, function), calls in _generated_calls().items():
        for call in calls:
            document = _keywords(call).get("document")
            where = f"{filename}:{call.lineno} ({function})"
            if document is None:
                missing.append(where)
            elif not isinstance(document, ast.Name) or document.id != "doc_name":
                wrong.append(f"{where}: {ast.unparse(document)}")

    assert not missing, "generated operations without document=doc_name:\n" + "\n".join(missing)
    assert not wrong, "generated operations with ambiguous document scope:\n" + "\n".join(wrong)


READ_ONLY_GENERATED_OPERATIONS = {
    ("core.py", "get_recompute_log_operation"),
    ("core.py", "get_sketch_diagnostics_operation"),
    ("diagnostics.py", "preview_attachment_operation"),
    ("diagnostics.py", "_find_subshapes_operation"),
    ("diagnostics.py", "_subshape_pose_operation"),
    ("diagnostics.py", "placement_audit_operation"),
    ("diagnostics.py", "capture_state_operation"),
    ("diagnostics.py", "geometric_diff_operation"),
    ("diagnostics.py", "audit_hardcoded_dimensions_operation"),
    ("diagnostics.py", "inspect_geometry_operation"),
    ("diagnostics.py", "get_dependency_graph_operation"),
    ("diagnostics.py", "match_subshape_operation"),
    ("interactive.py", "diagnose_pocket_operation"),
    ("interactive.py", "diagnose_helix_operation"),
    ("interactive.py", "compare_documents_operation"),
    ("p5_measure.py", "_run_read_analysis"),
    ("p6_io.py", "export_step_operation"),
    ("p6_io.py", "export_stl_operation"),
    ("p6_io.py", "export_brep_operation"),
    ("p7_assembly.py", "get_document_tree_operation"),
    ("p7_assembly.py", "get_sketch_geometry_operation"),
    ("parametric.py", "spreadsheet_get_cells_operation"),
    ("parametric.py", "spreadsheet_list_aliases_operation"),
    ("parametric.py", "list_expressions_operation"),
    ("parametric.py", "diagnose_parametric_operation"),
}


def test_generated_read_tools_request_snapshot_worker_compatible_execution() -> None:
    calls = _generated_calls()
    assert READ_ONLY_GENERATED_OPERATIONS <= calls.keys()

    failures: list[str] = []
    for key in sorted(READ_ONLY_GENERATED_OPERATIONS):
        for call in calls[key]:
            keywords = _keywords(call)
            if not _literal_true(keywords.get("read_only")):
                failures.append(f"{key[0]}:{call.lineno} ({key[1]}): missing read_only=True")
            if isinstance(call.func, ast.Name) and call.func.id == "_run_code":
                if _literal(keywords.get("recompute")) != "none":
                    failures.append(f"{key[0]}:{call.lineno} ({key[1]}): recompute is not 'none'")

    assert not failures, "\n".join(failures)


MUTATIONS_THAT_MUST_NOT_BE_MARKED_READ_ONLY = {
    ("core.py", "recompute_document_operation"),
    ("core.py", "undo_operation"),
    ("core.py", "redo_operation"),
    ("diagnostics.py", "relink_references_operation"),
    ("diagnostics.py", "create_placement_binder_operation"),
    ("diagnostics.py", "create_placement_datum_operation"),
    ("diagnostics.py", "run_transaction_operation"),
    ("diagnostics.py", "validate_movement_follow_operation"),
    ("p5_measure.py", "translate_operation"),
    ("p5_measure.py", "rotate_operation"),
    ("p5_measure.py", "scale_operation"),
    ("p6_io.py", "import_step_operation"),
    ("p6_io.py", "import_brep_operation"),
}


def test_stateful_operations_remain_live_document_mutations() -> None:
    calls = _generated_calls()
    assert MUTATIONS_THAT_MUST_NOT_BE_MARKED_READ_ONLY <= calls.keys()
    incorrectly_read_only = [
        f"{filename}:{call.lineno} ({function})"
        for (filename, function) in sorted(MUTATIONS_THAT_MUST_NOT_BE_MARKED_READ_ONLY)
        for call in calls[(filename, function)]
        if _literal_true(_keywords(call).get("read_only"))
    ]
    assert not incorrectly_read_only, "mutations marked read-only:\n" + "\n".join(
        incorrectly_read_only
    )


def _connection(message: str = "Output: {\"ok\": true}") -> MagicMock:
    connection = MagicMock()
    connection.execute_code.return_value = {
        "success": True,
        "message": message,
        "recompute_errors": [],
    }
    connection.get_active_screenshot.return_value = None
    return connection


@pytest.mark.parametrize("runner", [_run_code, _run_json_code])
def test_generated_mutation_helpers_emit_affected_document_credentials(runner) -> None:
    connection = _connection()
    if runner is _run_code:
        runner(connection, True, "print('ok')", "done", "failed", document="Doc")
    else:
        runner(connection, True, "print('{\"ok\": true}')", "failed", document="Doc")

    options = connection.execute_code.call_args.args[1]
    assert options.document == "Doc"
    assert options.affected_documents == ["Doc"]
    assert options.generated_operation is True
    assert options.read_only is False


@pytest.mark.parametrize("runner", [_run_code, _run_json_code])
def test_generated_read_helpers_use_worker_without_recompute(runner) -> None:
    connection = _connection()
    if runner is _run_code:
        runner(
            connection,
            True,
            "print('ok')",
            "done",
            "failed",
            document="Doc",
            read_only=True,
        )
    else:
        runner(
            connection,
            True,
            "print('{\"ok\": true}')",
            "failed",
            document="Doc",
            read_only=True,
        )

    options = connection.execute_code.call_args.args[1]
    assert options.document == "Doc"
    assert options.affected_documents is None
    assert options.read_only is True
    assert options.recompute == "none"
    assert options.execution_mode == "worker"
