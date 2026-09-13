"""Typed ``validate_movement_follow`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
from .typed_rpc_support import (
    add_named_object,
    add_to_container,
    as_bool,
    as_float,
    as_int,
    assign_attr,
    call_named,
    invoke,
    nonempty_string,
    object_label,
    object_name,
    object_type_id,
    optional_string,
    parse_ref,
    remove_from_container,
    require_object,
    resolve_if_exists,
    snapshot_ring
)


@dataclass(frozen=True, slots=True)
class ValidateMovementFollowReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
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


def apply_validate_movement_follow(doc: ValidateMovementFollowDocument, request: ValidateMovementFollowRequest) -> ValidateMovementFollowReceipt:
    """Apply a rigid transform to the source without recomputing."""

    source = require_object(doc, request.source, missing_code="OBJECT_NOT_FOUND", error=ValidateMovementFollowError)
    placement = getattr(source, "Placement", None)
    base = getattr(placement, "Base", None) if placement is not None else None
    if base is not None and isinstance(request.translation, list) and len(request.translation) >= 3:
        try:
            dx, dy, dz = (float(request.translation[0]), float(request.translation[1]), float(request.translation[2]))
            base.x = float(base.x) + dx
            base.y = float(base.y) + dy
            base.z = float(base.z) + dz
        except Exception:
            pass
    return ValidateMovementFollowReceipt(name=object_name(source) or request.source, item=source, skipped=False)


def read_validate_movement_follow_result(doc: ValidateMovementFollowReadDocument, receipt: ValidateMovementFollowReceipt) -> ValidateMovementFollowInspection:
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
        raise ValidateMovementFollowError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    extra = receipt.extra

    return ValidateMovementFollowInspection(
        name=ValidateMovementFollowName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_validate_movement_follow_request(doc_name: object, source: object, dependents: object, translation: object, axis: object, angle_deg: object, restore: object, tolerance: object) -> ValidateMovementFollowRequest | ValidateMovementFollowFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(ValidateMovementFollowError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    source_value = nonempty_string(source, 'source')
    if source_value is None:
        return _failure(ValidateMovementFollowError("INVALID_ARGUMENT", "source must be a nonempty string"))
    if not isinstance(dependents, list) or not dependents:
        return _failure(ValidateMovementFollowError("INVALID_ARGUMENT", "dependents must be a non-empty list"))
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
        dependents=dependents,
        translation=translation,
        axis=axis,
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
        return make_validate_movement_follow_success(source=self.inspected.name)


def run_validate_movement_follow(
    collaborators: ValidateMovementFollowCollaborators,
    doc_name: object, source: object, dependents: object, translation: object, axis: object, angle_deg: object, restore: object, tolerance: object,
) -> ValidateMovementFollowResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_validate_movement_follow_request(doc_name, source, dependents, translation, axis, angle_deg, restore, tolerance)
    if isinstance(request, dict):
        return request
    return _ValidateMovementFollowExecution(collaborators, request).run()


class _ValidateMovementFollowRpcFacade(Protocol):
    _cad_collaborators: ValidateMovementFollowCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_validate_movement_follow(
    self: _ValidateMovementFollowRpcFacade, doc_name: str, source: str, dependents: object, translation: object, axis: object, angle_deg: float, restore: bool = True, tolerance: float = 1e-07,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_validate_movement_follow(collaborators, doc_name, source, dependents, translation, axis, angle_deg, restore, tolerance)
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
