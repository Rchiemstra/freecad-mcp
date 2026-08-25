"""Stable structured validation results used across the evidence boundary."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationIssue:
    stage: str
    code: str
    artifact: str
    field: str


@dataclass(frozen=True)
class ValidationResult:
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.issues

    @property
    def issue(self) -> ValidationIssue | None:
        return self.issues[0] if self.issues else None

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls()

    @classmethod
    def fail(
        cls,
        stage: str,
        code: str,
        artifact: str,
        field: str,
    ) -> "ValidationResult":
        return cls((ValidationIssue(stage, code, artifact, field),))
