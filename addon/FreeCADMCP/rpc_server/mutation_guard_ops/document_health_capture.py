"""Document health capture and delta calculation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .document_health_delta import DocumentHealthDelta
from .document_health_snapshot import DocumentHealthSnapshot
from .document_health_verdict import DocumentHealthVerdict
from .object_helpers import (
    body_tip_issue,
    object_name,
    object_signature,
    object_state,
    shape_is_null,
    shape_is_valid,
)
from .validation_profile import ValidationProfile


def capture_document_health(
    document: Any,
    *,
    document_session_uuid: str = "",
    profile: ValidationProfile | str = ValidationProfile.DEFAULT,
    affected_objects: Iterable[str] = (),
) -> DocumentHealthSnapshot:
    selected = ValidationProfile(str(getattr(profile, "value", profile)))
    name = str(getattr(document, "Name", "") or "")
    if selected == ValidationProfile.NONE:
        return DocumentHealthSnapshot(
            document_name=name,
            document_session_uuid=str(document_session_uuid or ""),
            document_dirty=bool(getattr(document, "Modified", False)),
            object_count=len(tuple(getattr(document, "Objects", ()) or ())),
            object_names=(),
            recompute_error_objects=(),
            invalid_state_objects=(),
            null_shape_objects=(),
            invalid_shape_objects=(),
            body_tip_issues=(),
            validation_profile=selected.value,
            validation_available=False,
        )

    objects = tuple(getattr(document, "Objects", ()) or ())
    affected = {str(item) for item in affected_objects if str(item)}
    signatures: dict[str, tuple[Any, ...]] = {}
    recompute_errors: list[str] = []
    invalid_states: list[str] = []
    null_shapes: list[str] = []
    invalid_shapes: list[str] = []
    body_issues: list[str] = []
    names: list[str] = []
    for item in objects:
        item_name = object_name(item) or "<unnamed>"
        names.append(item_name)
        state = tuple(value.lower() for value in object_state(item))
        if any("error" in value for value in state):
            recompute_errors.append(item_name)
        if any("invalid" in value for value in state):
            invalid_states.append(item_name)
        signatures[item_name] = object_signature(
            item,
            include_shape_hash=selected
            in {ValidationProfile.DEFAULT, ValidationProfile.FULL},
        )
        shape_check = selected == ValidationProfile.FULL or (
            selected == ValidationProfile.DEFAULT and item_name in affected
        )
        if shape_check:
            is_null = shape_is_null(item)
            if is_null is True:
                null_shapes.append(item_name)
            elif is_null is False and shape_is_valid(item) is False:
                invalid_shapes.append(item_name)
        if selected in {ValidationProfile.DEFAULT, ValidationProfile.FULL}:
            issue = body_tip_issue(item)
            if issue:
                body_issues.append(issue)
    dirty = bool(
        getattr(
            document,
            "Modified",
            getattr(document, "modified", False),
        )
    )
    return DocumentHealthSnapshot(
        document_name=name,
        document_session_uuid=str(document_session_uuid or ""),
        document_dirty=dirty,
        object_count=len(objects),
        object_names=tuple(sorted(names)),
        recompute_error_objects=tuple(sorted(set(recompute_errors))),
        invalid_state_objects=tuple(sorted(set(invalid_states))),
        null_shape_objects=tuple(sorted(set(null_shapes))),
        invalid_shape_objects=tuple(sorted(set(invalid_shapes))),
        body_tip_issues=tuple(sorted(set(body_issues))),
        validation_profile=selected.value,
        validation_available=True,
        object_signatures=signatures,
    )


def calculate_document_health_delta(
    before: DocumentHealthSnapshot,
    after: DocumentHealthSnapshot,
    *,
    expected_modified_objects: Iterable[str] = (),
    validation_error: str | None = None,
) -> DocumentHealthDelta:
    before_names = set(before.object_names)
    after_names = set(after.object_names)
    created = after_names - before_names
    deleted = before_names - after_names
    shared = before_names.intersection(after_names)
    modified = {
        name
        for name in shared
        if before.object_signatures.get(name) != after.object_signatures.get(name)
    }
    expected = {str(item) for item in expected_modified_objects if str(item)}
    unexpected = modified.difference(expected)
    new_recompute = set(after.recompute_error_objects).difference(
        before.recompute_error_objects
    )
    resolved_recompute = set(before.recompute_error_objects).difference(
        after.recompute_error_objects
    )
    new_invalid_state = set(after.invalid_state_objects).difference(
        before.invalid_state_objects
    )
    new_null = set(after.null_shape_objects).difference(before.null_shape_objects)
    new_invalid_shape = set(after.invalid_shape_objects).difference(
        before.invalid_shape_objects
    )
    new_body_issues = set(after.body_tip_issues).difference(before.body_tip_issues)
    available = before.validation_available and after.validation_available
    if validation_error:
        verdict = DocumentHealthVerdict.INVALID
    elif not available:
        verdict = DocumentHealthVerdict.UNKNOWN
    elif (
        new_recompute
        or new_invalid_state
        or new_null
        or new_invalid_shape
        or new_body_issues
    ):
        verdict = DocumentHealthVerdict.DEGRADED
    elif (
        after.recompute_error_objects
        or after.invalid_state_objects
        or after.invalid_shape_objects
        or after.body_tip_issues
        or unexpected
    ):
        verdict = DocumentHealthVerdict.WARNING
    else:
        verdict = DocumentHealthVerdict.HEALTHY
    return DocumentHealthDelta(
        document_name=after.document_name or before.document_name,
        verdict=verdict,
        new_recompute_errors=tuple(sorted(new_recompute)),
        resolved_recompute_errors=tuple(sorted(resolved_recompute)),
        new_invalid_state_objects=tuple(sorted(new_invalid_state)),
        new_null_shapes=tuple(sorted(new_null)),
        new_invalid_shapes=tuple(sorted(new_invalid_shape)),
        created_objects=tuple(sorted(created)),
        deleted_objects=tuple(sorted(deleted)),
        modified_objects=tuple(sorted(modified)),
        unexpected_modified_objects=tuple(sorted(unexpected)),
        object_count_delta=after.object_count - before.object_count,
        preexisting_recompute_errors=before.recompute_error_objects,
        preexisting_invalid_state_objects=before.invalid_state_objects,
        preexisting_invalid_shapes=before.invalid_shape_objects,
        body_tip_issues=after.body_tip_issues,
        validation_profile=after.validation_profile,
        validation_available=available,
        validation_error=validation_error,
    )
