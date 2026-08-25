"""Immutable final-candidate construction and terminal publication."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .authorization import AuthorizationSnapshot, capture_terminal_authorization
from .bindings import ExecutionBinding
from .publication import publish_once
from .validation import ValidationResult


@dataclass(frozen=True)
class FinalCandidate:
    binding: ExecutionBinding
    result: str
    classification: str | None
    outer_execution_sha256: str
    ledger_sha256: str
    authorization_sha256: str
    signature_sha256: str
    ledger_members: tuple[str, ...]


def construct_final_candidate(
    output: Path,
    binding: ExecutionBinding,
    result: str,
    classification: str | None,
    ledger_members: tuple[str, ...],
) -> tuple[FinalCandidate | None, ValidationResult]:
    if result not in {"PASS", "FAIL"} or (result == "PASS" and classification is not None):
        return None, ValidationResult.fail("finalization", "FINAL_CANDIDATE_SCHEMA", "final-verdict.json", "/result")
    outer = output / "outer-execution.json"
    ledger = output / "artifact-ledger.json"
    if not outer.is_file():
        return None, ValidationResult.fail("finalization", "FINAL_CANDIDATE_MISSING", outer.name, "/")
    if not ledger.is_file():
        return None, ValidationResult.fail("finalization", "FINAL_CANDIDATE_MISSING", ledger.name, "/")
    return FinalCandidate(
        binding,
        result,
        classification,
        hashlib.sha256(outer.read_bytes()).hexdigest(),
        hashlib.sha256(ledger.read_bytes()).hexdigest(),
        binding.authorization_sha256,
        binding.signature_sha256,
        ledger_members,
    ), ValidationResult.ok()


def finalize(
    output: Path,
    candidate: FinalCandidate,
    prerequisites: tuple[Path, Path, Path],
    initial: AuthorizationSnapshot,
    now,
    interrupted: bool = False,
) -> ValidationResult:
    """After the terminal snapshot, perform no mutable read or callback."""
    terminal, result = capture_terminal_authorization(prerequisites, initial, now)
    if not result.passed or terminal is None:
        return result
    if (
        terminal.authorization_sha256 != candidate.authorization_sha256
        or terminal.signature_sha256 != candidate.signature_sha256
    ):
        return ValidationResult.fail("terminal_authorization", "AUTHORIZATION_HASH_CHANGED", "review-authorization.json", "/")
    if interrupted:
        return ValidationResult.fail("lifecycle", "TERMINAL_INTERRUPTED", "final-verdict.json", "/")
    verdict = {
        "schema_version": 44,
        "state": "FINAL_VERDICT",
        "result": candidate.result,
        "classification": candidate.classification,
        "binding": candidate.binding.as_dict(),
        "authorization_sha256": candidate.authorization_sha256,
        "signature_sha256": candidate.signature_sha256,
        "outer_execution_sha256": candidate.outer_execution_sha256,
        "ledger_sha256": candidate.ledger_sha256,
        "ledger_members": list(candidate.ledger_members),
        "terminal_authorization": {
            "valid": True,
            "authorization_sha256": terminal.authorization_sha256,
            "signature_sha256": terminal.signature_sha256,
        },
    }
    payload = json.dumps(verdict, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    return publish_once(output / "final-verdict.json", payload)
