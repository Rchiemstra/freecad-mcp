"""Document health delta between before/after mutation snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .document_health_verdict import DocumentHealthVerdict
from .validation_profile import ValidationProfile


@dataclass(frozen=True)
class DocumentHealthDelta:
    document_name: str
    verdict: DocumentHealthVerdict
    new_recompute_errors: tuple[str, ...] = ()
    resolved_recompute_errors: tuple[str, ...] = ()
    new_invalid_state_objects: tuple[str, ...] = ()
    new_null_shapes: tuple[str, ...] = ()
    new_invalid_shapes: tuple[str, ...] = ()
    created_objects: tuple[str, ...] = ()
    deleted_objects: tuple[str, ...] = ()
    modified_objects: tuple[str, ...] = ()
    unexpected_modified_objects: tuple[str, ...] = ()
    object_count_delta: int = 0
    preexisting_recompute_errors: tuple[str, ...] = ()
    preexisting_invalid_state_objects: tuple[str, ...] = ()
    preexisting_invalid_shapes: tuple[str, ...] = ()
    body_tip_issues: tuple[str, ...] = ()
    invalid_object_status: dict[str, str] | None = None
    validation_profile: str = ValidationProfile.DEFAULT.value
    validation_available: bool = True
    validation_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "document_name": self.document_name,
            "validation_profile": self.validation_profile,
            "validation_available": self.validation_available,
            "validation_error": self.validation_error,
            "new_recompute_errors": list(self.new_recompute_errors),
            "resolved_recompute_errors": list(self.resolved_recompute_errors),
            "new_invalid_state_objects": list(self.new_invalid_state_objects),
            "new_null_shapes": list(self.new_null_shapes),
            "new_invalid_shapes": list(self.new_invalid_shapes),
            "created_objects": list(self.created_objects),
            "deleted_objects": list(self.deleted_objects),
            "modified_objects": list(self.modified_objects),
            "unexpected_modified_objects": list(self.unexpected_modified_objects),
            "object_count_delta": self.object_count_delta,
            "preexisting_recompute_errors": list(self.preexisting_recompute_errors),
            "preexisting_invalid_state_objects": list(
                self.preexisting_invalid_state_objects
            ),
            "preexisting_invalid_shapes": list(self.preexisting_invalid_shapes),
            "body_tip_issues": list(self.body_tip_issues),
            "invalid_object_status": dict(self.invalid_object_status or {}),
        }
