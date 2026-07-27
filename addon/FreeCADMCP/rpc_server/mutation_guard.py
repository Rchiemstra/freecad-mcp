"""Typed mutation descriptors and GUI-thread transaction/postflight helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping

from .telemetry import emit as emit_telemetry


class RpcMutationKind(str, Enum):
    READ_ONLY = "read_only"
    LIVE_MUTATION = "live_mutation"
    SAVE = "save"
    RESTORE = "restore"
    CLOSE = "close"
    CONTROL = "control"


class ValidationProfile(str, Enum):
    NONE = "none"
    MINIMAL = "minimal"
    DEFAULT = "default"
    FULL = "full"


class DocumentHealthVerdict(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    DEGRADED = "degraded"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class RollbackCoverage(str, Enum):
    COMPLETE = "complete"
    DOCUMENT_ONLY = "document_only"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


def _object_name(value: Any) -> str:
    return str(getattr(value, "Name", "") or "")


def _object_state(value: Any) -> tuple[str, ...]:
    try:
        return tuple(sorted(str(item) for item in (getattr(value, "State", ()) or ())))
    except Exception:
        return ()


def _shape_hash(value: Any) -> str:
    shape = getattr(value, "Shape", None)
    if shape is None:
        return ""
    for name in ("hashCode", "HashCode"):
        method = getattr(shape, name, None)
        if callable(method):
            try:
                return str(method())
            except Exception:
                break
    try:
        return str(hash(shape))
    except Exception:
        return ""


def _shape_is_null(value: Any) -> bool | None:
    shape = getattr(value, "Shape", None)
    if shape is None:
        return None
    method = getattr(shape, "isNull", None)
    if not callable(method):
        return None
    try:
        return bool(method())
    except Exception:
        return None


def _shape_is_valid(value: Any) -> bool | None:
    shape = getattr(value, "Shape", None)
    if shape is None:
        return None
    method = getattr(shape, "isValid", None)
    if not callable(method):
        return None
    try:
        return bool(method())
    except Exception:
        return None


def _body_tip_issue(value: Any) -> str | None:
    try:
        is_body = value.isDerivedFrom("PartDesign::Body")
    except Exception:
        is_body = getattr(value, "TypeId", "") == "PartDesign::Body"
    if not is_body:
        return None
    group = tuple(getattr(value, "Group", ()) or ())
    tip = getattr(value, "Tip", None)
    if tip is None or tip in group:
        return None
    return f"{_object_name(value) or '<body>'}.Tip"


def _object_signature(value: Any, *, include_shape_hash: bool) -> tuple[Any, ...]:
    placement = getattr(value, "Placement", None)
    return (
        str(getattr(value, "TypeId", "") or ""),
        str(getattr(value, "Label", "") or ""),
        _object_state(value),
        bool(getattr(value, "Touched", False)),
        repr(placement)[:512] if placement is not None else "",
        _shape_hash(value) if include_shape_hash else "",
    )


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
            "unexpected_modified_objects": list(
                self.unexpected_modified_objects
            ),
            "object_count_delta": self.object_count_delta,
            "preexisting_recompute_errors": list(
                self.preexisting_recompute_errors
            ),
            "preexisting_invalid_state_objects": list(
                self.preexisting_invalid_state_objects
            ),
            "preexisting_invalid_shapes": list(
                self.preexisting_invalid_shapes
            ),
            "body_tip_issues": list(self.body_tip_issues),
        }


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
        item_name = _object_name(item) or "<unnamed>"
        names.append(item_name)
        state = tuple(value.lower() for value in _object_state(item))
        if any("error" in value for value in state):
            recompute_errors.append(item_name)
        if any("invalid" in value for value in state):
            invalid_states.append(item_name)
        signatures[item_name] = _object_signature(
            item,
            include_shape_hash=selected
            in {ValidationProfile.DEFAULT, ValidationProfile.FULL},
        )
        shape_check = selected == ValidationProfile.FULL or (
            selected == ValidationProfile.DEFAULT and item_name in affected
        )
        if shape_check:
            is_null = _shape_is_null(item)
            if is_null is True:
                null_shapes.append(item_name)
            elif is_null is False and _shape_is_valid(item) is False:
                invalid_shapes.append(item_name)
        if selected in {ValidationProfile.DEFAULT, ValidationProfile.FULL}:
            issue = _body_tip_issue(item)
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


@dataclass(frozen=True)
class RpcMethodSpec:
    name: str
    kind: RpcMutationKind
    transaction: bool = False
    recompute: bool = False
    validator: Callable[[Any], Mapping[str, Any]] | None = None
    may_rebind_document: bool = False
    allowed_during_recovery: bool = False
    pin_replay_for_lease_lifetime: bool = False
    validation_profile: ValidationProfile = ValidationProfile.DEFAULT
    rollback_coverage: RollbackCoverage = RollbackCoverage.DOCUMENT_ONLY

    @property
    def mutates_live_document(self) -> bool:
        return self.kind in {
            RpcMutationKind.LIVE_MUTATION,
            RpcMutationKind.SAVE,
            RpcMutationKind.RESTORE,
            RpcMutationKind.CLOSE,
        }


_NO_OUTER_TRANSACTION = frozenset(
    {
        "execute_code",
        "recompute_document",
        "recompute_and_wait",
        "undo",
        "redo",
        "reload_document",
        "restore",
        "close_document",
        "run_fem_analysis",
        "animate_placement",
        "repair_view_placements",
    }
)


_LEASE_LIFETIME_IDEMPOTENCY_METHODS = frozenset(
    {
        "acquire_document_lock",
        "update_document_lock",
        "lease_reconcile",
        "release_document_lock",
        "save_document",
        "save_document_as",
        "finalize_document_edit",
    }
)


def make_method_spec(name: str, kind: str) -> RpcMethodSpec:
    """Translate the exhaustive legacy verb registry into a richer descriptor."""

    normalized = str(kind).upper()
    if normalized == "READ_ONLY":
        return RpcMethodSpec(name, RpcMutationKind.READ_ONLY)
    if normalized == "LIFECYCLE":
        lifecycle_kind = (
            RpcMutationKind.SAVE
            if name in {"save_document", "save_document_as", "finalize_document_edit"}
            else RpcMutationKind.CONTROL
        )
        return RpcMethodSpec(
            name,
            lifecycle_kind,
            may_rebind_document=name in {"save_document_as", "finalize_document_edit"},
            pin_replay_for_lease_lifetime=(
                name in _LEASE_LIFETIME_IDEMPOTENCY_METHODS
            ),
        )
    partdesign_methods = {
        "body_create",
        "body_set_tip",
        "sketch_create",
        "sketch_add_geometry",
        "sketch_add_constraint",
        "sketch_attach",
        "sketch_edit_constraint",
        "pad_feature",
        "pocket_feature",
    }
    return RpcMethodSpec(
        name,
        RpcMutationKind.RESTORE
        if name in {"restore", "reload_document"}
        else RpcMutationKind.CLOSE
        if name == "close_document"
        else RpcMutationKind.LIVE_MUTATION,
        transaction=name not in _NO_OUTER_TRANSACTION,
        recompute=name in partdesign_methods,
        validator=(
            validate_document_invariants
            if name in partdesign_methods
            else None
        ),
        may_rebind_document=name in {"restore", "reload_document", "close_document"},
        allowed_during_recovery=name in {"restore"},
        pin_replay_for_lease_lifetime=True,
        validation_profile=(
            ValidationProfile.FULL
            if name in {"finalize_document_edit"}
            else ValidationProfile.DEFAULT
        ),
        rollback_coverage=(
            RollbackCoverage.PARTIAL
            if name
            in {
                "export_step",
                "export_stl",
                "export_brep",
                "save_document",
                "save_document_as",
                "finalize_document_edit",
            }
            else RollbackCoverage.UNAVAILABLE
            if name == "execute_code"
            else RollbackCoverage.DOCUMENT_ONLY
        ),
    )


def build_method_specs(
    classifications: Mapping[str, tuple[Any, Any]],
) -> dict[str, RpcMethodSpec]:
    return {
        name: make_method_spec(name, getattr(kind, "value", str(kind)))
        for name, (kind, _resolver) in classifications.items()
    }


class GuiMutationTransaction:
    """Open/commit or abort one named transaction on each declared document."""

    def __init__(self, documents: Iterable[Any], name: str, *, enabled: bool):
        self.documents = tuple(documents)
        self.name = str(name)[:128] or "MCP mutation"
        self.enabled = bool(enabled)
        self._opened: list[Any] = []
        self.started = False
        self.committed = False
        self.abort_attempted = False
        self.abort_succeeded: bool | None = None
        self.abort_errors: list[dict[str, str]] = []
        self._original_undo_modes: list[tuple[Any, Any]] = []

    def _ensure_undo_enabled(self, document: Any) -> None:
        """Enable FreeCAD transaction recording when a headless doc disabled it."""

        try:
            mode = getattr(document, "UndoMode")
        except (AttributeError, RuntimeError):
            # Test doubles and some legacy proxies expose transaction methods
            # without an UndoMode property.
            return
        try:
            disabled = int(mode) == 0
        except (TypeError, ValueError):
            disabled = mode is False
        if not disabled:
            return
        try:
            setattr(document, "UndoMode", 1)
        except Exception as exc:
            raise RuntimeError(
                f"cannot enable transaction recording for "
                f"{_object_name(document) or '<document>'}: {exc}"
            ) from exc
        self._original_undo_modes.append((document, mode))

    def _restore_undo_modes(self) -> None:
        while self._original_undo_modes:
            document, mode = self._original_undo_modes.pop()
            try:
                setattr(document, "UndoMode", mode)
            except Exception as exc:
                self.abort_errors.append(
                    {
                        "document": _object_name(document),
                        "error_type": type(exc).__name__,
                        "message": (
                            "could not restore document UndoMode: " + str(exc)
                        )[:1024],
                    }
                )

    def __enter__(self):
        if not self.enabled:
            return self
        try:
            for document in self.documents:
                self._ensure_undo_enabled(document)
                document.openTransaction(self.name)
                self._opened.append(document)
            self.started = bool(self._opened)
            emit_telemetry(
                "transaction",
                "transaction_started",
                payload={
                    "name": self.name,
                    "documents": [_object_name(item) for item in self.documents],
                    "enabled": self.enabled,
                },
            )
        except Exception:
            self.abort()
            raise
        return self

    def commit(self) -> None:
        try:
            while self._opened:
                self._opened.pop(0).commitTransaction()
        finally:
            self._restore_undo_modes()
        if self.enabled and self.started:
            self.committed = True
            emit_telemetry(
                "transaction",
                "transaction_committed",
                payload={
                    "name": self.name,
                    "documents": [_object_name(item) for item in self.documents],
                },
            )

    def abort(self) -> bool:
        if self.committed:
            return False
        self.abort_attempted = self.abort_attempted or bool(self._opened)
        while self._opened:
            document = self._opened.pop()
            try:
                document.abortTransaction()
            except Exception as exc:
                self.abort_errors.append(
                    {
                        "document": _object_name(document),
                        "error_type": type(exc).__name__,
                        "message": str(exc)[:1024],
                    }
                )
        self._restore_undo_modes()
        if self.abort_attempted:
            self.abort_succeeded = not self.abort_errors
            emit_telemetry(
                "transaction",
                (
                    "transaction_aborted"
                    if self.abort_succeeded
                    else "transaction_rollback_failed"
                ),
                status="succeeded" if self.abort_succeeded else "degraded",
                error_code=(
                    None
                    if self.abort_succeeded
                    else "TRANSACTION_ROLLBACK_FAILED"
                ),
                payload={
                    "name": self.name,
                    "documents": [_object_name(item) for item in self.documents],
                    "abort_errors": self.abort_errors,
                },
            )
        return bool(self.abort_succeeded)

    def to_dict(
        self,
        *,
        coverage: RollbackCoverage | str = RollbackCoverage.DOCUMENT_ONLY,
    ) -> dict[str, Any]:
        normalized_coverage = str(getattr(coverage, "value", coverage))
        if not self.enabled:
            status = "unavailable"
        elif self.committed:
            status = "committed"
        elif self.abort_attempted and self.abort_succeeded:
            status = "aborted"
        elif self.abort_attempted:
            status = "rollback_failed"
        elif self.started:
            status = "started"
        else:
            status = "not_started"
        return {
            "status": status,
            "enabled": self.enabled,
            "documents": [_object_name(item) for item in self.documents],
            "started": self.started,
            "committed": self.committed,
            "abort_attempted": self.abort_attempted,
            "abort_succeeded": self.abort_succeeded,
            "abort_errors": list(self.abort_errors),
            "rollback_attempted": self.abort_attempted,
            "rollback_succeeded": self.abort_succeeded,
            "coverage": normalized_coverage,
        }

    def __exit__(self, exc_type, _exc, _traceback):
        if exc_type is not None:
            self.abort()
        elif self._opened:
            self.commit()
        return False


def validate_document_invariants(document: Any) -> dict[str, Any]:
    """Check recompute errors and basic PartDesign Body/Tip invariants."""

    errors: list[str] = []
    body_checks: list[dict[str, Any]] = []
    for obj in getattr(document, "Objects", ()):
        state = [str(item).lower() for item in getattr(obj, "State", ())]
        if any("error" in item or "invalid" in item for item in state):
            errors.append(str(getattr(obj, "Name", "<unnamed>")))
        try:
            is_body = obj.isDerivedFrom("PartDesign::Body")
        except Exception:
            is_body = getattr(obj, "TypeId", "") == "PartDesign::Body"
        if not is_body:
            continue
        group = tuple(getattr(obj, "Group", ()) or ())
        tip = getattr(obj, "Tip", None)
        tip_valid = tip is None or tip in group
        if not tip_valid:
            errors.append(f"{getattr(obj, 'Name', '<body>')}.Tip")
        body_checks.append(
            {
                "body": str(getattr(obj, "Name", "")),
                "member_count": len(group),
                "tip": getattr(tip, "Name", None),
                "tip_is_member": tip_valid,
            }
        )
    if errors:
        raise RuntimeError(
            "Document postflight validation failed: " + ", ".join(sorted(set(errors)))
        )
    return {"ok": True, "body_checks": body_checks}


__all__ = [
    "DocumentHealthDelta",
    "DocumentHealthSnapshot",
    "DocumentHealthVerdict",
    "GuiMutationTransaction",
    "RollbackCoverage",
    "RpcMethodSpec",
    "RpcMutationKind",
    "ValidationProfile",
    "build_method_specs",
    "calculate_document_health_delta",
    "capture_document_health",
    "make_method_spec",
    "validate_document_invariants",
]
