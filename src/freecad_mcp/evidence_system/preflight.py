"""Strict schema-44 preflight parser and semantic validator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any

from .bindings import ExecutionBinding
from .policy import EvidencePolicy, PREFLIGHT_CHECKS
from .validation import ValidationResult

ARTIFACT = "preflight.json"
TOP_LEVEL_FIELDS = {"schema_version", "binding", "observed_utc", "passed", "checks", "commands", "output_fresh"}


def parse_json_bytes(raw: bytes) -> Any:
    def reject_duplicates(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in rows:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value

    return json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)


def command_hash(commands: dict[str, list[str]]) -> str:
    wire = json.dumps(commands, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(wire).hexdigest()


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def validate_preflight(
    value: Any,
    expected: ExecutionBinding,
    policy: EvidencePolicy,
    now: datetime | None = None,
) -> ValidationResult:
    if not isinstance(value, dict) or set(value) != TOP_LEVEL_FIELDS:
        return ValidationResult.fail("preflight", "PREFLIGHT_SCHEMA", ARTIFACT, "/")
    if not isinstance(value["schema_version"], int) or isinstance(value["schema_version"], bool) or value["schema_version"] != 44:
        return ValidationResult.fail("preflight", "PREFLIGHT_SCHEMA_VERSION", ARTIFACT, "/schema_version")

    binding, result = ExecutionBinding.parse(value["binding"], ARTIFACT)
    if not result.passed:
        return result
    if binding != expected:
        return ValidationResult.fail("binding", "EXECUTION_BINDING_MISMATCH", ARTIFACT, "/binding")

    observed = _time(value["observed_utc"])
    current = now or datetime.now(timezone.utc)
    if observed is None or observed < current - timedelta(seconds=policy.max_age_seconds) or observed > current + timedelta(seconds=policy.future_skew_seconds):
        return ValidationResult.fail("preflight", "PREFLIGHT_TIMESTAMP_FRESHNESS", ARTIFACT, "/observed_utc")

    semantic_values = {
        "package": expected.package_manifest,
        "authorization": {"authorization_sha256": expected.authorization_sha256, "signature_sha256": expected.signature_sha256},
        "configured_candidate": expected.configured_candidate,
        "raw_candidate": expected.raw_candidate,
        "repository": expected.repository,
        "sources": policy.sources,
        "binaries": policy.binaries,
        "image": expected.image,
        "output_freshness": True,
        "conflicting_processes": [],
        "port": {"available": True},
        "cache": {"clean": True},
        "resolved_outer_command": list(policy.outer_argv),
        "resolved_executor_command": list(policy.executor_argv),
        "resolved_docker_command": list(policy.docker_argv),
        "environment": policy.environment,
        "mounts": list(policy.mounts),
        "timestamp_freshness": True,
    }
    checks = value["checks"]
    if not isinstance(checks, list) or len(checks) != len(PREFLIGHT_CHECKS):
        return ValidationResult.fail("preflight", "PREFLIGHT_REQUIRED_CHECKS", ARTIFACT, "/checks")
    seen: set[str] = set()
    for index, check in enumerate(checks):
        field = f"/checks/{index}"
        if not isinstance(check, dict) or set(check) != {"id", "status", "binding", "value"}:
            return ValidationResult.fail("preflight", "PREFLIGHT_CHECK_SCHEMA", ARTIFACT, field)
        check_id = check["id"]
        if not isinstance(check_id, str) or check_id not in PREFLIGHT_CHECKS or check_id in seen:
            return ValidationResult.fail("preflight", "PREFLIGHT_CHECK_ID", ARTIFACT, field + "/id")
        if check["status"] not in {"PASS", "FAIL"}:
            return ValidationResult.fail("preflight", "PREFLIGHT_CHECK_STATUS", ARTIFACT, field + "/status")
        check_binding, bound = ExecutionBinding.parse(check["binding"], ARTIFACT, field + "/binding")
        if not bound.passed:
            return bound
        if check_binding != expected:
            return ValidationResult.fail("binding", "EXECUTION_BINDING_MISMATCH", ARTIFACT, field + "/binding")
        semantic_passed = check["value"] == semantic_values[check_id]
        if check["status"] != ("PASS" if semantic_passed else "FAIL") or not semantic_passed:
            return ValidationResult.fail(
                "preflight", "PREFLIGHT_" + check_id.upper() + "_FAILED", ARTIFACT, field + "/value"
            )
        seen.add(check_id)
    if seen != set(PREFLIGHT_CHECKS):
        return ValidationResult.fail("preflight", "PREFLIGHT_REQUIRED_CHECKS", ARTIFACT, "/checks")

    commands = value["commands"]
    if not isinstance(commands, dict) or set(commands) != {"outer", "executor", "docker"}:
        return ValidationResult.fail("preflight", "PREFLIGHT_COMMAND_SCHEMA", ARTIFACT, "/commands")
    expected_commands = {
        "outer": list(policy.outer_argv),
        "executor": list(policy.executor_argv),
        "docker": list(policy.docker_argv),
    }
    if commands != expected_commands:
        return ValidationResult.fail("preflight", "PREFLIGHT_COMMAND_CONTRACT", ARTIFACT, "/commands")
    if command_hash(commands) != expected.commands:
        return ValidationResult.fail("preflight", "PREFLIGHT_COMMAND_BINDING", ARTIFACT, "/commands")

    if not isinstance(value["output_fresh"], bool):
        return ValidationResult.fail("preflight", "PREFLIGHT_OUTPUT_FRESHNESS_TYPE", ARTIFACT, "/output_fresh")
    if not isinstance(value["passed"], bool):
        return ValidationResult.fail("preflight", "PREFLIGHT_DERIVED_PASS_TYPE", ARTIFACT, "/passed")
    derived = value["output_fresh"] and all(check["status"] == "PASS" for check in checks)
    if value["passed"] != derived:
        return ValidationResult.fail("preflight", "PREFLIGHT_DERIVED_PASS_MISMATCH", ARTIFACT, "/passed")
    if not derived:
        return ValidationResult.fail("preflight", "PREFLIGHT_OUTPUT_NOT_FRESH", ARTIFACT, "/output_fresh")
    return ValidationResult.ok()


def validate(
    raw: bytes,
    expected: ExecutionBinding | dict[str, object],
    policy: EvidencePolicy,
    now: datetime | None = None,
) -> ValidationResult:
    try:
        value = parse_json_bytes(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return ValidationResult.fail("preflight", "PREFLIGHT_JSON", ARTIFACT, "/")
    if isinstance(expected, dict):
        expected, parsed = ExecutionBinding.parse(expected, ARTIFACT)
        if not parsed.passed or expected is None:
            return parsed
    return validate_preflight(value, expected, policy, now)
