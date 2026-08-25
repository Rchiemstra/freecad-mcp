"""Exact ledger-v2 construction and verification."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .bindings import ExecutionBinding
from .validation import ValidationResult


def build_ledger(output: Path, binding: ExecutionBinding, members: tuple[str, ...]) -> tuple[dict[str, Any] | None, ValidationResult]:
    entries: dict[str, dict[str, Any]] = {}
    for name in members:
        path = output / name
        if not path.is_file():
            return None, ValidationResult.fail("ledger", "LEDGER_MISSING_ARTIFACT", name, "/entries")
        data = path.read_bytes()
        entries[name] = {
            "path": name,
            "type": "file",
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "binding": binding.as_dict(),
        }
    return {"schema_version": 2, "binding": binding.as_dict(), "entries": entries}, ValidationResult.ok()


def validate_ledger(value: Any, output: Path, binding: ExecutionBinding, members: tuple[str, ...]) -> ValidationResult:
    if not isinstance(value, dict) or set(value) != {"schema_version", "binding", "entries"} or value["schema_version"] != 2:
        return ValidationResult.fail("ledger", "LEDGER_SCHEMA", "artifact-ledger.json", "/")
    if value["binding"] != binding.as_dict():
        return ValidationResult.fail("ledger", "LEDGER_BINDING", "artifact-ledger.json", "/binding")
    entries = value["entries"]
    if not isinstance(entries, dict) or set(entries) != set(members):
        return ValidationResult.fail("ledger", "LEDGER_COMPLETENESS", "artifact-ledger.json", "/entries")
    for name, row in entries.items():
        field = "/entries/" + name
        if not isinstance(row, dict) or set(row) != {"path", "type", "size", "sha256", "binding"}:
            return ValidationResult.fail("ledger", "LEDGER_ENTRY_SCHEMA", "artifact-ledger.json", field)
        if row["path"] != name or row["type"] != "file" or not isinstance(row["size"], int) or isinstance(row["size"], bool) or row["binding"] != binding.as_dict():
            return ValidationResult.fail("ledger", "LEDGER_ENTRY_SCHEMA", "artifact-ledger.json", field)
    rebuilt, result = build_ledger(output, binding, members)
    if not result.passed:
        return result
    if rebuilt != value:
        return ValidationResult.fail("ledger", "LEDGER_HASH_MISMATCH", "artifact-ledger.json", "/entries")
    return ValidationResult.ok()
