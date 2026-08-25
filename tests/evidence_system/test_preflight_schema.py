"""Schema-44 preflight mutations; each test reaches its named guard."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import hashlib

from freecad_mcp.evidence_system.bindings import ExecutionBinding
from freecad_mcp.evidence_system.policy import EvidencePolicy, PREFLIGHT_CHECKS
from freecad_mcp.evidence_system.preflight import command_hash, validate
from tests.evidence_system.packet_harness import run_packet

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
COMMANDS = {
    "outer": [str(PY), "-I", "-S", "-B", str(ROOT / "trusted-bootstrap.py"), "--interpreter-sha256", PYHASH],
    "executor": [str(PY), "-I", "-S", "-B", str(ROOT / "executor.py")],
    "docker": [str(PY), "run", "--network", "none"],
}
POLICY = EvidencePolicy(
    run_id="P3-WP27",
    attempt_id="tracked-evidence-tests",
    sequence=44,
    reviewer_key=HEX,
    scope="tracked-evidence-scope/44",
    interpreter=str(PY),
    outer_argv=tuple(COMMANDS["outer"]),
    executor_argv=tuple(COMMANDS["executor"]),
    docker_argv=tuple(COMMANDS["docker"]),
    environment={},
    mounts=MOUNTS,
    sources={"runner.py": HEX},
    binaries={"host_interpreter": PYHASH},
)
BINDING = ExecutionBinding(
    "P3-WP27", "tracked-evidence-tests", 44, HEX, "C:/out", HEX, HEX, HEX,
    "sha256:" + HEX, HEX, HEX, command_hash(COMMANDS), "tracked-evidence-scope/44", HEX, HEX, HEX,
    NOW.isoformat(),
)


def packet() -> dict[str, object]:
    binding = BINDING.as_dict()
    values = {
        "package": BINDING.package_manifest,
        "authorization": {"authorization_sha256": BINDING.authorization_sha256, "signature_sha256": BINDING.signature_sha256},
        "configured_candidate": BINDING.configured_candidate, "raw_candidate": BINDING.raw_candidate,
        "repository": BINDING.repository, "sources": POLICY.sources, "binaries": POLICY.binaries,
        "image": BINDING.image, "output_freshness": True, "conflicting_processes": [],
        "port": {"available": True}, "cache": {"clean": True},
        "resolved_outer_command": list(POLICY.outer_argv), "resolved_executor_command": list(POLICY.executor_argv),
        "resolved_docker_command": list(POLICY.docker_argv), "environment": POLICY.environment,
        "mounts": list(POLICY.mounts), "timestamp_freshness": True,
    }
    return {
        "schema_version": 44,
        "binding": binding,
        "observed_utc": NOW.isoformat(),
        "passed": True,
        "checks": [{"id": check, "status": "PASS", "binding": binding, "value": values[check]} for check in PREFLIGHT_CHECKS],
        "commands": COMMANDS,
        "output_fresh": True,
    }


def reject(tmp_path, check_id: str, expected_code: str) -> None:
    result, output = run_packet(tmp_path, {"kind": "preflight", "check": check_id})
    assert result["passed"] is False
    assert result["issue"] == {"stage": "preflight", "code": expected_code, "artifact": "preflight.json", "field": "/checks/%d/value" % PREFLIGHT_CHECKS.index(check_id)}
    assert not (output / "final-verdict.json").exists()


def test_package_check_failure_reaches_package_guard(tmp_path):
    reject(tmp_path, "package", "PREFLIGHT_PACKAGE_FAILED")
    duplicate = validate(b'{"schema_version":44,"schema_version":44}', BINDING, POLICY, NOW)
    assert duplicate.issue is not None
    assert (duplicate.issue.stage, duplicate.issue.code, duplicate.issue.artifact, duplicate.issue.field) == ("preflight", "PREFLIGHT_JSON", "preflight.json", "/")


def test_authorization_check_failure_reaches_authorization_guard(tmp_path):
    reject(tmp_path, "authorization", "PREFLIGHT_AUTHORIZATION_FAILED")


def test_configured_candidate_failure_reaches_configured_candidate_guard(tmp_path):
    reject(tmp_path, "configured_candidate", "PREFLIGHT_CONFIGURED_CANDIDATE_FAILED")


def test_raw_candidate_failure_reaches_raw_candidate_guard(tmp_path):
    reject(tmp_path, "raw_candidate", "PREFLIGHT_RAW_CANDIDATE_FAILED")


def test_repository_failure_reaches_repository_guard(tmp_path):
    reject(tmp_path, "repository", "PREFLIGHT_REPOSITORY_FAILED")


def test_sources_failure_reaches_sources_guard(tmp_path):
    reject(tmp_path, "sources", "PREFLIGHT_SOURCES_FAILED")


def test_binaries_failure_reaches_binaries_guard(tmp_path):
    reject(tmp_path, "binaries", "PREFLIGHT_BINARIES_FAILED")


def test_image_failure_reaches_image_guard(tmp_path):
    reject(tmp_path, "image", "PREFLIGHT_IMAGE_FAILED")


def test_output_freshness_failure_reaches_output_freshness_guard(tmp_path):
    reject(tmp_path, "output_freshness", "PREFLIGHT_OUTPUT_FRESHNESS_FAILED")


def test_conflicting_process_failure_reaches_process_guard(tmp_path):
    reject(tmp_path, "conflicting_processes", "PREFLIGHT_CONFLICTING_PROCESSES_FAILED")


def test_port_failure_reaches_port_guard(tmp_path):
    reject(tmp_path, "port", "PREFLIGHT_PORT_FAILED")


def test_cache_failure_reaches_cache_guard(tmp_path):
    reject(tmp_path, "cache", "PREFLIGHT_CACHE_FAILED")


def test_outer_command_failure_reaches_outer_command_guard(tmp_path):
    reject(tmp_path, "resolved_outer_command", "PREFLIGHT_RESOLVED_OUTER_COMMAND_FAILED")


def test_executor_command_failure_reaches_executor_command_guard(tmp_path):
    reject(tmp_path, "resolved_executor_command", "PREFLIGHT_RESOLVED_EXECUTOR_COMMAND_FAILED")


def test_docker_command_failure_reaches_docker_command_guard(tmp_path):
    reject(tmp_path, "resolved_docker_command", "PREFLIGHT_RESOLVED_DOCKER_COMMAND_FAILED")


def test_environment_failure_reaches_environment_guard(tmp_path):
    reject(tmp_path, "environment", "PREFLIGHT_ENVIRONMENT_FAILED")


def test_mount_failure_reaches_mount_guard(tmp_path):
    reject(tmp_path, "mounts", "PREFLIGHT_MOUNTS_FAILED")


def test_stale_timestamp_reaches_timestamp_freshness_guard(tmp_path):
    result, output = run_packet(tmp_path, {"kind": "preflight", "check": "timestamp_freshness"})
    assert result["issue"] == {"stage": "preflight", "code": "PREFLIGHT_TIMESTAMP_FRESHNESS", "artifact": "preflight.json", "field": "/observed_utc"}
    assert not (output / "final-verdict.json").exists()
