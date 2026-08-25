"""Child mutations traverse trusted bootstrap and the authoritative reducer."""
from __future__ import annotations

from tests.evidence_system.packet_harness import run_packet


def _case(tmp_path, name, code, artifact):
    result, out = run_packet(tmp_path, {"kind": "child", "case": name})
    assert result["passed"] is False
    field = "/status" if code in {"CHILD_RESULT_STATUS", "CHILD_RESULT_CONTRADICTION", "CHILD_PARENT_EXIT_DISAGREEMENT"} else "/binding" if code == "CHILD_RESULT_BINDING" else "/"
    assert result["issue"] == {"stage": "child", "code": code, "artifact": artifact, "field": field}
    assert not (out / "final-verdict.json").exists()


def test_complete_success_packet_reconciles(tmp_path):
    result, out = run_packet(tmp_path)
    assert result["passed"] is True and (out / "final-verdict.json").is_file()


def test_missing_gdb_phase_is_rejected(tmp_path): _case(tmp_path, "missing_gdb", "CHILD_MISSING_REQUIRED_PHASE", "gdb-resolution.json")
def test_missing_localization_phase_is_rejected(tmp_path): _case(tmp_path, "missing_localization", "CHILD_MISSING_REQUIRED_PHASE", "localization-result.json")
def test_missing_terminal_result_is_rejected(tmp_path): _case(tmp_path, "missing_terminal", "CHILD_TERMINAL_CARDINALITY", "child-results")
def test_success_and_failure_terminals_are_rejected_as_multiplicity(tmp_path): _case(tmp_path, "multiple", "CHILD_TERMINAL_CARDINALITY", "child-results")
def test_unknown_result_shaped_artifact_is_rejected(tmp_path): _case(tmp_path, "unknown", "CHILD_UNKNOWN_RESULT_ARTIFACT", "foreign-result.json")
def test_malformed_result_json_is_rejected(tmp_path): _case(tmp_path, "malformed", "CHILD_RESULT_JSON", "gdb-resolution.json")
def test_added_result_field_is_rejected(tmp_path): _case(tmp_path, "added", "CHILD_RESULT_SCHEMA", "gdb-resolution.json")
def test_unknown_result_status_is_rejected(tmp_path): _case(tmp_path, "status", "CHILD_RESULT_STATUS", "localization-result.json")
def test_foreign_execution_binding_is_rejected(tmp_path): _case(tmp_path, "foreign", "CHILD_RESULT_BINDING", "gdb-resolution.json")
def test_foreign_container_identity_is_rejected(tmp_path): _case(tmp_path, "foreign_container", "CHILD_RESULT_BINDING", "gdb-resolution.json")
def test_success_terminal_contradicting_failed_phase_is_rejected(tmp_path): _case(tmp_path, "contradiction", "CHILD_RESULT_CONTRADICTION", "child-terminal-result.json")
def test_failure_terminal_disagrees_with_zero_parent_exit(tmp_path): _case(tmp_path, "parent", "CHILD_PARENT_EXIT_DISAGREEMENT", "child-failure-result.json")
def test_failure_terminal_with_nonzero_parent_exit_reduces_to_fail(tmp_path):
    result, out = run_packet(tmp_path, {"kind":"child","case":"failure"})
    assert result["passed"] is True and __import__("json").loads((out / "final-verdict.json").read_text())["result"] == "FAIL"
