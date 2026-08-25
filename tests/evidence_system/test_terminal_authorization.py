"""Terminal authorization mutations through the ordered production runner."""
from __future__ import annotations

import base64
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

from freecad_mcp.evidence_system.bindings import AuthorizationBinding, ContainerExecutionBinding, ExecutionBinding
from freecad_mcp.evidence_system.child_results import ChildResultRegistry, REGISTRY_CONFIG
from freecad_mcp.evidence_system.policy import EvidencePolicy, PREFLIGHT_CHECKS
from freecad_mcp.evidence_system.preflight import command_hash
from freecad_mcp.evidence_system.runner import EvidenceRunner, RunContext
from tests.evidence_system.non_authoritative_signing import sign

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
HEX = "a" * 64
ROOT = Path(__file__).resolve().parents[2]; PY = Path(sys.executable).resolve(); PYHASH = hashlib.sha256(PY.read_bytes()).hexdigest()
MOUNTS = (
    {"Type": "bind", "Source": str(ROOT / "package"), "Destination": "/diagnostic", "RW": False},
    {"Type": "bind", "Source": str(ROOT / "trusted-bootstrap.py"), "Destination": "/trusted/bootstrap.py", "RW": False},
    {"Type": "bind", "Source": str(ROOT), "Destination": "/repo", "RW": False},
    {"Type": "bind", "Source": str(ROOT), "Destination": "/build", "RW": False},
    {"Type": "bind", "Source": str(ROOT / "out"), "Destination": "/out", "RW": True},
)
DOCKER_LAUNCH = [str(PY), "run", "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=2g"] + [item for row in MOUNTS for item in ("--mount", f"type=bind,src={row['Source']},dst={row['Destination']}" + ("" if row["RW"] else ",readonly"))] + ["sha256:" + HEX]
COMMANDS = {"outer": [str(PY), "-I", "-S", "-B", str(ROOT / "trusted-bootstrap.py"), "--interpreter-sha256", PYHASH], "executor": [str(PY), "-I", "-S", "-B", str(ROOT / "executor.py")], "docker": DOCKER_LAUNCH}


def make_context(tmp_path, after_initial=None, terminal_now=None, child_status="SUCCEEDED"):
    prerequisites = tmp_path / "prerequisites"; prerequisites.mkdir()
    public, _ = sign(b"")
    reviewer = hashlib.sha256(public).hexdigest()
    direct = AuthorizationBinding(
        "P3-WP27", "tracked-evidence-tests", 44, HEX, str(tmp_path / "out"), HEX, HEX, HEX,
        "sha256:" + HEX, HEX, HEX, command_hash(COMMANDS), "tracked-evidence-scope/44", reviewer,
    )
    document = {
        "schema_version": 2, "status": "AUTHORIZED", **direct.as_dict(),
        "not_before_utc": (NOW - timedelta(seconds=1)).isoformat(),
        "issued_utc": NOW.isoformat(), "expires_utc": (NOW + timedelta(minutes=5)).isoformat(),
    }
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    public, signature = sign(raw)
    wire = b"\0\0\0\vssh-ed25519\0\0\0 " + public
    authorization = prerequisites / "review-authorization.json"; authorization.write_bytes(raw)
    signature_path = prerequisites / "review-authorization.sig"; signature_path.write_bytes(base64.b64encode(signature))
    public_path = prerequisites / "reviewer.pub"; public_path.write_text("ssh-ed25519 " + base64.b64encode(wire).decode())
    binding = ExecutionBinding.from_snapshot(raw, signature, NOW.isoformat(), direct)
    policy = EvidencePolicy(direct.run_id, direct.attempt_id, direct.sequence, direct.reviewer_key, "tracked-evidence-scope/44", str(PY), tuple(COMMANDS["outer"]), tuple(COMMANDS["executor"]), tuple(COMMANDS["docker"]), {}, MOUNTS, {}, {"host_interpreter": PYHASH})
    values = {
        "package": binding.package_manifest,
        "authorization": {"authorization_sha256": binding.authorization_sha256, "signature_sha256": binding.signature_sha256},
        "configured_candidate": binding.configured_candidate, "raw_candidate": binding.raw_candidate,
        "repository": binding.repository, "sources": policy.sources, "binaries": policy.binaries,
        "image": binding.image, "output_freshness": True, "conflicting_processes": [],
        "port": {"available": True}, "cache": {"clean": True},
        "resolved_outer_command": list(policy.outer_argv), "resolved_executor_command": list(policy.executor_argv),
        "resolved_docker_command": list(policy.docker_argv), "environment": policy.environment,
        "mounts": list(policy.mounts), "timestamp_freshness": True,
    }
    packet = {
        "schema_version": 44, "binding": binding.as_dict(), "observed_utc": NOW.isoformat(), "passed": True,
        "checks": [{"id": name, "status": "PASS", "binding": binding.as_dict(), "value": values[name]} for name in PREFLIGHT_CHECKS],
        "commands": COMMANDS, "output_fresh": True,
    }

    def execute(output, actual):
        inspect = {"Id": "b" * 64, "Config": {"Image": actual.image, "Entrypoint": list(policy.container_entrypoint), "Cmd": list(policy.container_cmd), "Env": []}, "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True, "Tmpfs": {"/tmp": "rw,nosuid,nodev,size=2g"}}, "Mounts": [dict(row) for row in MOUNTS]}
        raw_inspect = json.dumps(inspect, sort_keys=True, separators=(",", ":"))
        inspect["_raw_bytes"] = raw_inspect
        container = ContainerExecutionBinding(actual, "b" * 64, hashlib.sha256(raw_inspect.encode()).hexdigest())
        phases = (("gdb-resolution.json", "gdb_resolution", "SUCCEEDED"), ("localization-result.json", "localization", "SUCCEEDED"))
        terminal_name = "child-terminal-result.json" if child_status == "SUCCEEDED" else "child-failure-result.json"
        phases += ((terminal_name, "terminal", child_status),)
        for name, phase, status in phases:
            value = {"schema_version": 44, "binding": container.as_dict(), "phase": phase, "status": status}
            (output / name).write_text(json.dumps(value))
        return {"status": child_status, "docker": {"launch": DOCKER_LAUNCH, "inspect": inspect, "kernel_tmpfs": "rw,nosuid,nodev,size=2g"}}, 0 if child_status == "SUCCEEDED" else 1, container

    context = RunContext(
        tmp_path / "out", (authorization, signature_path, public_path), direct, policy,
        json.dumps(packet).encode(), ChildResultRegistry.from_signed_config(REGISTRY_CONFIG), execute,
        lambda output, actual: {"passed": True, "errors": []}, NOW, after_initial=after_initial, terminal_now=terminal_now or (lambda: NOW),
    )
    return context, document, authorization, signature_path


def assert_issue(result, context, expected):
    assert result.issue is not None
    assert (result.issue.stage, result.issue.code, result.issue.artifact, result.issue.field) == expected
    assert not result.passed and not (context.output / "final-verdict.json").exists()


def test_terminal_authorization_unchanged_allows_one_pass(tmp_path):
    context, _, _, _ = make_context(tmp_path)
    assert EvidenceRunner().run(context).passed


def test_terminal_authorization_document_mutation_is_rejected(tmp_path):
    holder = {}
    def mutate(): holder["authorization"].write_bytes(b"{}")
    context, _, authorization, _ = make_context(tmp_path, mutate); holder["authorization"] = authorization
    assert_issue(EvidenceRunner().run(context), context, ("authorization", "AUTHORIZATION_SCHEMA", "review-authorization.json", "/"))


def test_terminal_authorization_signature_mutation_is_rejected(tmp_path):
    holder = {}
    def mutate(): holder["signature"].write_bytes(base64.b64encode(b"\0" * 64))
    context, _, _, signature = make_context(tmp_path, mutate); holder["signature"] = signature
    assert_issue(EvidenceRunner().run(context), context, ("authorization", "AUTHORIZATION_SIGNATURE", "review-authorization.json", "/"))


def test_terminal_authorization_valid_replacement_is_rejected(tmp_path):
    holder = {}
    def mutate():
        document = dict(holder["document"]); document["issued_utc"] = (NOW - timedelta(milliseconds=500)).isoformat()
        raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode(); _, signature = sign(raw)
        holder["authorization"].write_bytes(raw); holder["signature"].write_bytes(base64.b64encode(signature))
    context, document, authorization, signature = make_context(tmp_path, mutate)
    holder.update(document=document, authorization=authorization, signature=signature)
    assert_issue(EvidenceRunner().run(context), context, ("terminal_authorization", "AUTHORIZATION_CHANGED", "review-authorization.json", "/"))


def test_terminal_authorization_truncation_is_rejected(tmp_path):
    holder = {}
    def mutate(): holder["authorization"].write_bytes(b"{")
    context, _, authorization, _ = make_context(tmp_path, mutate); holder["authorization"] = authorization
    assert_issue(EvidenceRunner().run(context), context, ("authorization", "AUTHORIZATION_SCHEMA", "review-authorization.json", "/"))


def test_foreign_policy_identity_cannot_publish_pass(tmp_path):
    base = tmp_path / "policy"; base.mkdir(); policy_context, _, _, _ = make_context(base)
    foreign = replace(policy_context.authorization_binding, scope="foreign-scope")
    rejected = EvidenceRunner().run(replace(policy_context, authorization_binding=foreign))
    assert_issue(rejected, policy_context, ("authorization", "AUTHORIZATION_POLICY_IDENTITY", "review-authorization.json", "/"))


def test_terminal_command_replacement_is_rejected(tmp_path):
    holder = {}
    def mutate():
        document = dict(holder["document"]); document["commands"] = "d" * 64
        raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode(); _, signature = sign(raw)
        holder["authorization"].write_bytes(raw); holder["signature"].write_bytes(base64.b64encode(signature))
    context, document, authorization, signature = make_context(tmp_path, mutate)
    holder.update(document=document, authorization=authorization, signature=signature)
    assert_issue(EvidenceRunner().run(context), context, ("authorization", "AUTHORIZATION_BINDING", "review-authorization.json", "/"))


def test_terminal_mid_run_expiry_is_rejected_with_fresh_terminal_time(tmp_path):
    context, _, _, _ = make_context(tmp_path, terminal_now=lambda: NOW + timedelta(minutes=6))
    assert_issue(EvidenceRunner().run(context), context, ("authorization", "AUTHORIZATION_EXPIRED", "review-authorization.json", "/expires_utc"))


def test_final_verdict_binds_terminal_authorization_hashes(tmp_path):
    context, _, _, _ = make_context(tmp_path)
    assert EvidenceRunner().run(context).passed
    verdict = json.loads((context.output / "final-verdict.json").read_text())
    assert verdict["authorization_sha256"] == verdict["terminal_authorization"]["authorization_sha256"]
    assert verdict["signature_sha256"] == verdict["terminal_authorization"]["signature_sha256"]
