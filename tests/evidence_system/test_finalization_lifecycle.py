"""Write-once lifecycle and seven deterministic interruption boundaries."""
from __future__ import annotations

from dataclasses import replace
import json

from freecad_mcp.evidence_system.bindings import ContainerExecutionBinding, ExecutionBinding
from freecad_mcp.evidence_system.finalization import construct_final_candidate
from freecad_mcp.evidence_system.ledger import build_ledger, validate_ledger
from freecad_mcp.evidence_system.publication import publish_once
from freecad_mcp.evidence_system.runner import EvidenceRunner, _validate_outer
from tests.evidence_system.test_terminal_authorization import make_context


def binding_from(context) -> ExecutionBinding:
    value = json.loads(context.preflight)["binding"]
    binding, result = ExecutionBinding.parse(value, "preflight.json")
    assert result.passed and binding is not None
    return binding


def assert_no_pass(context, result, expected=None) -> None:
    assert not result.passed
    assert result.issue is not None
    if expected is not None:
        assert (result.issue.stage, result.issue.code, result.issue.artifact, result.issue.field) == expected
    verdict = context.output / "final-verdict.json"
    if verdict.exists():
        try:
            value = json.loads(verdict.read_text())
        except (OSError, json.JSONDecodeError):
            return  # A preserved stale byte sequence is not a valid final PASS.
        assert value.get("result") != "PASS"


def test_fresh_output_completes_with_create_only_verdict(tmp_path):
    context, _, _, _ = make_context(tmp_path)
    assert EvidenceRunner().run(context).passed
    assert json.loads((context.output / "final-verdict.json").read_text())["result"] == "PASS"
    failed_root = tmp_path / "child-failure"; failed_root.mkdir()
    failed, _, _, _ = make_context(failed_root, child_status="FAILED")
    assert EvidenceRunner().run(failed).passed
    assert json.loads((failed.output / "final-verdict.json").read_text())["result"] == "FAIL"
    assert "child-failure-result.json" in json.loads((failed.output / "artifact-ledger.json").read_text())["entries"]


def test_stale_outer_ledger_and_verdict_each_preserve_directory_without_execution(tmp_path):
    for name in ("outer-execution.json", "artifact-ledger.json", "final-verdict.json"):
        base = tmp_path / name.replace(".json", ""); base.mkdir()
        context, _, _, _ = make_context(base)
        context.output.mkdir(); stale = context.output / name; stale.write_bytes(b"preserve")
        called = []
        result = EvidenceRunner().run(replace(context, execute=lambda *_: called.append(True)))  # type: ignore[arg-type]
        assert_no_pass(context, result, ("lifecycle", "OUTPUT_STALE", name, "/"))
        assert stale.read_bytes() == b"preserve" and not called


def test_missing_outer_prevents_final_candidate(tmp_path):
    context, _, _, _ = make_context(tmp_path); context.output.mkdir()
    (context.output / "artifact-ledger.json").write_text("{}")
    candidate, result = construct_final_candidate(context.output, binding_from(context), "PASS", None, ())
    assert candidate is None
    assert_no_pass(context, result, ("finalization", "FINAL_CANDIDATE_MISSING", "outer-execution.json", "/"))


def test_malformed_outer_packet_is_rejected(tmp_path):
    context, _, _, _ = make_context(tmp_path); binding = binding_from(context)
    container = ContainerExecutionBinding(binding, "b" * 64, "c" * 64)
    result = _validate_outer({"schema_version": 44}, binding, container)
    assert result.issue is not None
    assert (result.issue.stage, result.issue.code, result.issue.artifact, result.issue.field) == ("outer", "OUTER_SCHEMA", "outer-execution.json", "/")
    foreign_root = tmp_path / "foreign"; foreign_root.mkdir()
    context, _, _, _ = make_context(foreign_root)
    def foreign_execute(output, actual):
        return {}, 0, ContainerExecutionBinding(ExecutionBinding(**{**actual.as_dict(), "nonce": "d" * 64}), "b" * 64, "c" * 64)
    rejected = EvidenceRunner().run(replace(context, execute=foreign_execute))
    assert_no_pass(context, rejected, ("binding", "CONTAINER_EXECUTION_BINDING_MISMATCH", "outer-execution.json", "/container_binding/execution"))


def test_post_hash_member_mutation_invalidates_ledger(tmp_path):
    context, _, _, _ = make_context(tmp_path); binding = binding_from(context); context.output.mkdir()
    member = context.output / "outer-execution.json"; member.write_bytes(b"before")
    ledger, result = build_ledger(context.output, binding, (member.name,)); assert result.passed and ledger is not None
    member.write_bytes(b"after")
    checked = validate_ledger(ledger, context.output, binding, (member.name,))
    assert checked.issue is not None
    assert (checked.issue.stage, checked.issue.code, checked.issue.artifact, checked.issue.field) == ("ledger", "LEDGER_HASH_MISMATCH", "artifact-ledger.json", "/entries")
    assert not (context.output / "final-verdict.json").exists()


def test_incomplete_and_empty_ledgers_are_rejected(tmp_path):
    context, _, _, _ = make_context(tmp_path); binding = binding_from(context); context.output.mkdir()
    member = context.output / "outer-execution.json"; member.write_bytes(b"x")
    for entries in ({}, {"foreign": {}}):
        value = {"schema_version": 2, "binding": binding.as_dict(), "entries": entries}
        result = validate_ledger(value, context.output, binding, (member.name,))
        assert result.issue is not None
        assert (result.issue.stage, result.issue.code, result.issue.artifact, result.issue.field) == ("ledger", "LEDGER_COMPLETENESS", "artifact-ledger.json", "/entries")
        assert not (context.output / "final-verdict.json").exists()


def test_cleanup_contradiction_is_rejected(tmp_path):
    context, _, _, _ = make_context(tmp_path); binding = binding_from(context)
    container = ContainerExecutionBinding(binding, "b" * 64, "c" * 64)
    outer = {"schema_version": 44, "binding": binding.as_dict(), "container_binding": container.as_dict(), "parent_exit": 0, "execution": {}, "cleanup": {"passed": True, "errors": ["container_alive"]}}
    result = _validate_outer(outer, binding, container)
    assert result.issue is not None
    assert (result.issue.stage, result.issue.code, result.issue.artifact, result.issue.field) == ("outer", "OUTER_CLEANUP_CONTRADICTION", "outer-execution.json", "/cleanup")
    base = tmp_path / "coherent"; base.mkdir(); context, _, _, _ = make_context(base)
    failed = EvidenceRunner().run(replace(context, cleanup=lambda *_: {"passed": False, "errors": ["container_alive"]}))
    assert_no_pass(context, failed, ("aftermath", "CLEANUP_FAILED", "outer-execution.json", "/cleanup/passed"))
    assert (context.output / "outer-execution.json").is_file()


def test_create_only_publication_never_overwrites_existing_bytes(tmp_path):
    artifact = tmp_path / "outer-execution.json"; artifact.write_bytes(b"original")
    result = publish_once(artifact, b"replacement")
    assert result.issue is not None
    assert (result.issue.stage, result.issue.code, result.issue.artifact, result.issue.field) == ("lifecycle", "ARTIFACT_ALREADY_EXISTS", "outer-execution.json", "/")
    assert artifact.read_bytes() == b"original"


def interruption_case(tmp_path, boundary: str) -> None:
    context, _, _, _ = make_context(tmp_path)
    result = EvidenceRunner().run(replace(context, failpoint=boundary))
    expected = ("lifecycle", "TERMINAL_INTERRUPTED", "final-verdict.json", "/") if boundary == "before_verdict" else ("lifecycle", "LIFECYCLE_INTERRUPTED", "final-verdict.json", "/" + boundary)
    assert_no_pass(context, result, expected)


def test_interruption_after_freshness_cannot_publish_pass(tmp_path):
    interruption_case(tmp_path, "after_freshness")


def test_interruption_after_initial_authorization_cannot_publish_pass(tmp_path):
    interruption_case(tmp_path, "after_initial_authorization")


def test_interruption_after_execution_cannot_publish_pass(tmp_path):
    context, _, _, _ = make_context(tmp_path); events = []
    result = EvidenceRunner().run(replace(context, execute=lambda output, binding: (events.append("execute"), context.execute(output, binding))[1], cleanup=lambda output, binding: (events.append("cleanup"), {"passed": True, "errors": []})[1], failpoint="after_execution"))
    assert_no_pass(context, result, ("lifecycle", "LIFECYCLE_INTERRUPTED", "final-verdict.json", "/after_execution"))
    assert events == ["execute"]
    assert not (context.output / "outer-execution.json").exists()


def test_interruption_after_cleanup_cannot_publish_pass(tmp_path):
    context, _, _, _ = make_context(tmp_path); events = []
    result = EvidenceRunner().run(replace(context, execute=lambda output, binding: (events.append("execute"), context.execute(output, binding))[1], cleanup=lambda output, binding: (events.append("cleanup"), {"passed": True, "errors": []})[1], failpoint="after_cleanup"))
    assert_no_pass(context, result, ("lifecycle", "LIFECYCLE_INTERRUPTED", "final-verdict.json", "/after_cleanup"))
    assert events == ["execute", "cleanup"]
    assert not (context.output / "outer-execution.json").exists()


def test_interruption_after_outer_publication_cannot_publish_pass(tmp_path):
    interruption_case(tmp_path, "after_outer")


def test_interruption_after_ledger_publication_cannot_publish_pass(tmp_path):
    interruption_case(tmp_path, "after_ledger")


def test_interruption_before_verdict_publication_cannot_publish_pass(tmp_path):
    interruption_case(tmp_path, "before_verdict")
