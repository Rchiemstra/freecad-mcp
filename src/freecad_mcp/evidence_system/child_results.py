"""Config-owned child-result registry and sole authoritative reducer."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .bindings import ContainerExecutionBinding
from .validation import ValidationResult

REGISTRY_CONFIG = {
    "gdb-resolution.json": {"role": "phase", "phase": "gdb_resolution", "required": True, "statuses": ["FAILED", "SUCCEEDED"], "multiplicity": 1},
    "localization-result.json": {"role": "phase", "phase": "localization", "required": True, "statuses": ["FAILED", "SUCCEEDED"], "multiplicity": 1},
    "child-terminal-result.json": {"role": "terminal", "phase": "terminal", "required": False, "statuses": ["SUCCEEDED"], "multiplicity": 1},
    "child-failure-result.json": {"role": "terminal", "phase": "terminal", "required": False, "statuses": ["FAILED"], "multiplicity": 1},
}


@dataclass(frozen=True)
class ChildResultRegistry:
    entries: Mapping[str, Mapping[str, object]]

    @classmethod
    def from_signed_config(cls, value: Any) -> "ChildResultRegistry":
        if value != REGISTRY_CONFIG:
            raise ValueError("child result registry")
        return cls(REGISTRY_CONFIG)


@dataclass(frozen=True)
class ChildReconciliation:
    """The single reducer for child phases and the terminal child record."""

    validation: ValidationResult
    result: str | None = None
    classification: str | None = None
    ledger_members: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.validation.passed

    @property
    def issue(self):
        return self.validation.issue


SUCCESS_LEDGER_MEMBERS = (
    "gdb-resolution.json", "localization-result.json", "child-terminal-result.json", "outer-execution.json",
)
FAILURE_LEDGER_MEMBERS = (
    "gdb-resolution.json", "localization-result.json", "child-failure-result.json", "outer-execution.json",
)


def _rejected(result: ValidationResult) -> ChildReconciliation:
    return ChildReconciliation(result)


def _read_record(path: Path, expected: ContainerExecutionBinding, spec: Mapping[str, object]) -> tuple[dict[str, Any] | None, ValidationResult]:
    def reject_duplicates(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in rows:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None, ValidationResult.fail("child", "CHILD_RESULT_JSON", path.name, "/")
    if not isinstance(value, dict) or set(value) != {"schema_version", "binding", "phase", "status"} or value["schema_version"] != 44:
        return None, ValidationResult.fail("child", "CHILD_RESULT_SCHEMA", path.name, "/")
    if value["phase"] != spec["phase"]:
        return None, ValidationResult.fail("child", "CHILD_RESULT_PHASE", path.name, "/phase")
    if not isinstance(value["status"], str) or value["status"] not in spec["statuses"]:
        return None, ValidationResult.fail("child", "CHILD_RESULT_STATUS", path.name, "/status")
    binding, result = ContainerExecutionBinding.parse(value["binding"], path.name)
    if not result.passed:
        return None, result
    if binding != expected:
        return None, ValidationResult.fail("child", "CHILD_RESULT_BINDING", path.name, "/binding")
    return value, ValidationResult.ok()


def reconcile_child_results(
    output: Path,
    binding: ContainerExecutionBinding,
    parent_exit: int,
    registry: ChildResultRegistry,
) -> ChildReconciliation:
    try:
        entries = [entry for entry in output.iterdir() if entry.is_file()]
    except OSError:
        return _rejected(ValidationResult.fail("child", "CHILD_RESULTS_UNREADABLE", "child-results", "/"))
    governed = [
        entry for entry in entries
        if entry.name in registry.entries
        or entry.name.endswith("-result.json")
        or entry.name in {"gdb-resolution.json", "localization-result.json"}
    ]
    unknown = sorted(entry.name for entry in governed if entry.name not in registry.entries)
    if unknown:
        return _rejected(ValidationResult.fail("child", "CHILD_UNKNOWN_RESULT_ARTIFACT", unknown[0], "/"))
    by_name = {entry.name: entry for entry in governed}
    for name, spec in registry.entries.items():
        if spec["required"] and name not in by_name:
            return _rejected(ValidationResult.fail("child", "CHILD_MISSING_REQUIRED_PHASE", name, "/"))
    terminals = [name for name in ("child-terminal-result.json", "child-failure-result.json") if name in by_name]
    if len(terminals) != 1:
        return _rejected(ValidationResult.fail("child", "CHILD_TERMINAL_CARDINALITY", "child-results", "/"))

    records: dict[str, dict[str, Any]] = {}
    for name in registry.entries:
        if name not in by_name:
            continue
        record, result = _read_record(by_name[name], binding, registry.entries[name])
        if not result.passed or record is None:
            return _rejected(result)
        records[name] = record

    failed_phases = [name for name in ("gdb-resolution.json", "localization-result.json") if records[name]["status"] != "SUCCEEDED"]
    terminal = records[terminals[0]]["status"]
    if failed_phases and terminal == "SUCCEEDED":
        return _rejected(ValidationResult.fail("child", "CHILD_RESULT_CONTRADICTION", terminals[0], "/status"))
    expected_exit = 0 if terminal == "SUCCEEDED" else 1
    if (parent_exit == 0) != (expected_exit == 0):
        return _rejected(ValidationResult.fail("child", "CHILD_PARENT_EXIT_DISAGREEMENT", terminals[0], "/status"))
    if terminal == "FAILED":
        # A coherent child failure is a valid final FAIL, not a validation error.
        return ChildReconciliation(ValidationResult.ok(), "FAIL", "CHILD_FAILURE", FAILURE_LEDGER_MEMBERS)
    if failed_phases:
        return _rejected(ValidationResult.fail("child", "CHILD_PHASE_FAILURE", failed_phases[0], "/status"))
    return ChildReconciliation(ValidationResult.ok(), "PASS", None, SUCCESS_LEDGER_MEMBERS)
