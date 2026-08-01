"""Immutable document health snapshot captured before/after mutations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DocumentHealthSnapshot:
    document_name: str
    document_session_uuid: str
    document_dirty: bool
    object_count: int
    object_names: tuple[str, ...]
    recompute_error_objects: tuple[str, ...]
    invalid_state_objects: tuple[str, ...]
    null_shape_objects: tuple[str, ...]
    invalid_shape_objects: tuple[str, ...]
    body_tip_issues: tuple[str, ...]
    validation_profile: str
    validation_available: bool = True
    object_signatures: Mapping[str, tuple[Any, ...]] = field(
        default_factory=dict, repr=False, compare=False
    )

    def to_dict(self, *, include_signatures: bool = False) -> dict[str, Any]:
        result = {
            "document_name": self.document_name,
            "document_session_uuid": self.document_session_uuid or None,
            "document_dirty": self.document_dirty,
            "object_count": self.object_count,
            "object_names": list(self.object_names),
            "recompute_error_objects": list(self.recompute_error_objects),
            "invalid_state_objects": list(self.invalid_state_objects),
            "null_shape_objects": list(self.null_shape_objects),
            "invalid_shape_objects": list(self.invalid_shape_objects),
            "body_tip_issues": list(self.body_tip_issues),
            "validation_profile": self.validation_profile,
            "validation_available": self.validation_available,
        }
        if include_signatures:
            result["object_signatures"] = {
                name: list(signature)
                for name, signature in self.object_signatures.items()
            }
        return result
