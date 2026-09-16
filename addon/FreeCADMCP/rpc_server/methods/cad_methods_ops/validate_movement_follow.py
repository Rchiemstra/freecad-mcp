
"""Typed ``validate_movement_follow`` mutation."""
from __future__ import annotations

from .typed_rpc_support import (
    as_bool,
    as_float,
    nonempty_string,
    object_label,
    object_name,
    require_object,
)

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Protocol

from ...._shared.protocol.validate_movement_follow_contract import (
    ValidateMovementFollowCollaborators,
    ValidateMovementFollowDocument,
    ValidateMovementFollowFailure,
    ValidateMovementFollowName,
    ValidateMovementFollowReadDocument,
    ValidateMovementFollowRequest,
    ValidateMovementFollowResult,
    DocumentName,
    make_validate_movement_follow_failure,
    make_validate_movement_follow_success,
    make_validate_movement_follow_uncertain,
)
from .validate_movement_follow_mutation import ValidateMovementFollowError, run_validate_movement_follow_native_mutation



@dataclass(frozen=True, slots=True)
class ValidateMovementFollowReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    document: object | None = None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class ValidateMovementFollowInspection:
    """Read-only data captured after the native-owned recompute."""

    name: ValidateMovementFollowName
    label: str
    extra: object = None


def _failure(error: ValidateMovementFollowError, *, retry_safe: bool = True) -> ValidateMovementFollowFailure:
    return make_validate_movement_follow_failure(error.code, str(error), retry_safe=retry_safe)


def _as_xyz(value: object) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    out: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        out.append(float(item))
    return out


def _placement_base_tuple(placement: object | None) -> tuple[float, float, float] | None:
    base = getattr(placement, "Base", None) if placement is not None else None
    if base is None:
        return None
    return (float(base.x), float(base.y), float(base.z))


def _copy_placement(placement: object) -> object:
    copy_method = getattr(placement, "copy", None)
    if callable(copy_method):
        try:
            return copy_method()
        except Exception:
            pass
    base = getattr(placement, "Base", None)
    rotation = getattr(placement, "Rotation", None)
    copied_base = SimpleNamespace(
        x=float(getattr(base, "x", 0.0)),
        y=float(getattr(base, "y", 0.0)),
        z=float(getattr(base, "z", 0.0)),
    )
    copied = SimpleNamespace(Base=copied_base)
    if rotation is not None:
        copied.Rotation = rotation
    return copied


def _apply_placement_delta(
    placement: object | None,
    translation: list[float],
    axis: list[float],
    angle_deg: float,
) -> object | None:
    if placement is None:
        return None
    updated = _copy_placement(placement)
    base = getattr(updated, "Base", None)
    tx = [float(translation[0]), float(translation[1]), float(translation[2])]
    if base is not None:
        base.x = float(base.x) + tx[0]
        base.y = float(base.y) + tx[1]
        base.z = float(base.z) + tx[2]
    if abs(float(angle_deg)) > 1e-12:
        rotation = getattr(updated, "Rotation", None)
        if rotation is not None:
            rotator = getattr(rotation, "rotate", None)
            if callable(rotator):
                rotator(axis, float(angle_deg))
    return updated


def _restore_saved_placements(doc: object, originals: dict[str, object]) -> None:
    getter = getattr(doc, "getObject", None)
    if not callable(getter):
        return
    for name, placement in originals.items():
        obj = getter(name)
        if obj is not None:
            setattr(obj, "Placement", placement)


def apply_validate_movement_follow(
    doc: ValidateMovementFollowDocument,
    request: ValidateMovementFollowRequest,
) -> ValidateMovementFollowReceipt:
    """Apply a rigid transform to the source and dependents without recomputing."""

    source = require_object(doc, request.source, missing_code="OBJECT_NOT_FOUND", error=ValidateMovementFollowError)
    originals: dict[str, object] = {}
    names_to_move = [request.source]
    for dependent in request.dependents:
        if isinstance(dependent, str) and dependent not in names_to_move:
            names_to_move.append(dependent)
    source_before = _placement_base_tuple(getattr(source, "Placement", None))
    for name in names_to_move:
        obj = require_object(doc, name, missing_code="OBJECT_NOT_FOUND", error=ValidateMovementFollowError)
        placement = getattr(obj, "Placement", None)
        if placement is not None:
            originals[name] = _copy_placement(placement)
    source_placement = getattr(source, "Placement", None)
    updated_source = _apply_placement_delta(
        source_placement,
        request.translation,
        request.axis,
        request.angle_deg,
    )
    if updated_source is not None:
        setattr(source, "Placement", updated_source)
    source_after = _placement_base_tuple(getattr(source, "Placement", None))
    delta: tuple[float, float, float] | None = None
    if source_before is not None and source_after is not None:
        delta = (
            source_after[0] - source_before[0],
            source_after[1] - source_before[1],
            source_after[2] - source_before[2],
        )
    for dependent in request.dependents:
        if dependent == request.source:
            continue
        dependent_obj = require_object(
            doc,
            dependent,
            missing_code="OBJECT_NOT_FOUND",
            error=ValidateMovementFollowError,
        )
        dependent_placement = getattr(dependent_obj, "Placement", None)
        updated_dependent = _apply_placement_delta(
            dependent_placement,
            request.translation,
            request.axis,
            request.angle_deg,
        )
        if updated_dependent is not None:
            setattr(dependent_obj, "Placement", updated_dependent)
    return ValidateMovementFollowReceipt(
        name=object_name(source) or request.source,
        item=source,
        document=doc,
        skipped=False,
        extra={
            "originals": originals,
            "restore": request.restore,
            "delta": delta,
            "dependents": list(request.dependents),
            "tolerance": request.tolerance,
        },
    )


def read_validate_movement_follow_result(
    doc: ValidateMovementFollowReadDocument,
    receipt: ValidateMovementFollowReceipt,
) -> ValidateMovementFollowInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise ValidateMovementFollowError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise ValidateMovementFollowError(
            "CREATED_OBJECT_REPLACED",
            f"Target was replaced before commit: {receipt.name!r}",
        )
    extra_data = receipt.extra if isinstance(receipt.extra, dict) else {}
    restore = extra_data.get("restore") is True
    dependents = extra_data.get("dependents")
    delta = extra_data.get("delta")
    tolerance = extra_data.get("tolerance")
    originals = extra_data.get("originals")
    follow: dict[str, object] = {}
    if isinstance(dependents, list):
        for dependent in dependents:
            if not isinstance(dependent, str) or not dependent:
                continue
            dependent_obj = doc.getObject(dependent)
            if dependent_obj is None:
                raise ValidateMovementFollowError("OBJECT_NOT_FOUND", f"Dependent is missing: {dependent!r}")
            if restore:
                continue
            if not isinstance(delta, tuple) or len(delta) != 3:
                continue
            placement = getattr(dependent_obj, "Placement", None)
            current_base = _placement_base_tuple(placement)
            original = originals.get(dependent) if isinstance(originals, dict) else None
            original_base = _placement_base_tuple(original)
            if current_base is None or original_base is None:
                continue
            tol = float(tolerance) if isinstance(tolerance, (int, float)) else 1e-07
            moved = all(
                abs((current_base[index] - original_base[index]) - float(delta[index])) <= tol
                for index in range(3)
            )
            follow[dependent] = moved
    extra = follow if follow else extra_data.get("follow")
    return ValidateMovementFollowInspection(
        name=ValidateMovementFollowName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_validate_movement_follow_request(
    doc_name: object,
    source: object,
    dependents: object,
    translation: object,
    axis: object,
    angle_deg: object,
    restore: object,
    tolerance: object,
) -> ValidateMovementFollowRequest | ValidateMovementFollowFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(ValidateMovementFollowError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    source_value = nonempty_string(source, 'source')
    if source_value is None:
        return _failure(ValidateMovementFollowError("INVALID_ARGUMENT", "source must be a nonempty string"))
    if not isinstance(dependents, list) or not dependents:
        return _failure(ValidateMovementFollowError("INVALID_ARGUMENT", "dependents must be a non-empty list"))
    dependent_names: list[str] = []
    for dependent in dependents:
        if not isinstance(dependent, str) or not dependent.strip():
            return _failure(ValidateMovementFollowError("INVALID_ARGUMENT", "dependents must be a list of strings"))
        dependent_names.append(dependent)
    translation_values = _as_xyz(translation)
    if translation_values is None:
        return _failure(ValidateMovementFollowError("INVALID_ARGUMENT", "translation must be a sequence of 3 numbers"))
    axis_values = _as_xyz(axis)
    if axis_values is None:
        return _failure(ValidateMovementFollowError("INVALID_ARGUMENT", "axis must be a sequence of 3 numbers"))
    angle_deg_value = as_float(angle_deg, None)
    if angle_deg_value is None:
        return _failure(ValidateMovementFollowError("INVALID_ARGUMENT", "angle_deg must be a number"))
    restore_value = as_bool(restore, True)
    if restore_value is None:
        return _failure(ValidateMovementFollowError("INVALID_ARGUMENT", "restore must be a boolean"))
    tolerance_value = as_float(tolerance, 1e-07)
    if tolerance_value is None:
        return _failure(ValidateMovementFollowError("INVALID_ARGUMENT", "tolerance must be a number"))
    return ValidateMovementFollowRequest(
        doc_name=DocumentName(doc_name_value),
        source=source_value,
        dependents=dependent_names,
        translation=translation_values,
        axis=axis_values,
        angle_deg=angle_deg_value,
        restore=restore_value,
        tolerance=tolerance_value,
    )


@dataclass(slots=True)
class _ValidateMovementFollowExecution:
    collaborators: ValidateMovementFollowCollaborators
    request: ValidateMovementFollowRequest
    created: ValidateMovementFollowReceipt | None = None
    inspected: ValidateMovementFollowInspection | None = None

    def apply(self, doc: ValidateMovementFollowDocument) -> None:
        self.created = apply_validate_movement_follow(doc, self.request)

    def inspect(self, doc: ValidateMovementFollowReadDocument) -> None:
        if self.created is None:
            raise ValidateMovementFollowError(
                "INVALID_VALIDATE_MOVEMENT_FOLLOW_RESULT",
                "validate_movement_follow did not return an identity receipt",
            )
        self.inspected = read_validate_movement_follow_result(doc, self.created)

    def run(self) -> ValidateMovementFollowResult:
        result = run_validate_movement_follow_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_validate_movement_follow_uncertain(
                "VALIDATE_MOVEMENT_FOLLOW_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        if self.request.restore and self.created is not None:
            extra = self.created.extra
            if isinstance(extra, dict):
                originals = extra.get("originals")
                if isinstance(originals, dict):
                    doc = self.created.document
                    if doc is None:
                        doc = self.created.item
                    app = getattr(self.collaborators, "freecad", None)
                    if app is not None:
                        getter = getattr(app, "getDocument", None)
                        if callable(getter):
                            try:
                                live_doc = getter(str(self.request.doc_name))
                            except Exception:
                                live_doc = None
                            if live_doc is not None:
                                doc = live_doc
                    if doc is not None:
                        _restore_saved_placements(doc, originals)
        return make_validate_movement_follow_success(source=self.inspected.name)


def run_validate_movement_follow(
    collaborators: ValidateMovementFollowCollaborators,
    doc_name: object,
    source: object,
    dependents: object,
    translation: object,
    axis: object,
    angle_deg: object,
    restore: object,
    tolerance: object,
) -> ValidateMovementFollowResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_validate_movement_follow_request(
        doc_name,
        source,
        dependents,
        translation,
        axis,
        angle_deg,
        restore,
        tolerance,
    )
    if isinstance(request, dict):
        return request
    return _ValidateMovementFollowExecution(collaborators, request).run()


class _ValidateMovementFollowRpcFacade(Protocol):
    _cad_collaborators: ValidateMovementFollowCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_validate_movement_follow(
    self: _ValidateMovementFollowRpcFacade,
    doc_name: str,
    source: str,
    dependents: object,
    translation: object,
    axis: object,
    angle_deg: float,
    restore: bool = True,
    tolerance: float = 1e-07,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_validate_movement_follow(
            collaborators,
            doc_name,
            source,
            dependents,
            translation,
            axis,
            angle_deg,
            restore,
            tolerance,
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("validate_movement_follow", rpc_validate_movement_follow)


__all__ = [
    "ValidateMovementFollowCollaborators",
    "ValidateMovementFollowError",
    "ValidateMovementFollowInspection",
    "ValidateMovementFollowReceipt",
    "apply_validate_movement_follow",
    "build_validate_movement_follow_request",
    "read_validate_movement_follow_result",
    "rpc_validate_movement_follow",
    "run_validate_movement_follow",
    "TYPED_RPC_HANDLER",
]
