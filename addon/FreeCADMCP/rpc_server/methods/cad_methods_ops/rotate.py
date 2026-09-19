"""Typed ``rotate`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.rotate_contract import (
        ObjectName,
        DocumentName,
        RotateCollaborators,
        RotateFailure,
        RotateRequest,
        RotateResult,
        MutationDocument,
        MutationObject,
        MutationReadDocument,
        make_rotate_failure,
        make_rotate_success,
        make_rotate_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.rotate_contract import (
        ObjectName,
        DocumentName,
        RotateCollaborators,
        RotateFailure,
        RotateRequest,
        RotateResult,
        MutationDocument,
        MutationObject,
        MutationReadDocument,
        make_rotate_failure,
        make_rotate_success,
        make_rotate_uncertain,
    )
from .typed_runtime import as_float, as_int, as_str
from . import measure_io_actions
from .rotate_mutation import RotateError, run_rotate_native_mutation


@dataclass(frozen=True, slots=True)
class RotateReceipt:
    payload: dict[str, object]
    obj: MutationObject | None
    expected: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class RotateInspection:
    payload: dict[str, object]


def _failure(error: RotateError, *, retry_safe: bool = True) -> RotateFailure:
    return make_rotate_failure(error.code, str(error), retry_safe=retry_safe)


def build_rotate_request(
    doc_name: object, obj_name: object, axis_x: object, axis_y: object, axis_z: object, angle_deg: object, center_x: object, center_y: object, center_z: object
) -> RotateRequest | RotateFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(RotateError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(RotateError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    if isinstance(axis_x, bool) or not isinstance(axis_x, (int, float)):
        return _failure(RotateError("INVALID_ARGUMENT", "axis_x must be a number"))
    if isinstance(axis_y, bool) or not isinstance(axis_y, (int, float)):
        return _failure(RotateError("INVALID_ARGUMENT", "axis_y must be a number"))
    if isinstance(axis_z, bool) or not isinstance(axis_z, (int, float)):
        return _failure(RotateError("INVALID_ARGUMENT", "axis_z must be a number"))
    if isinstance(angle_deg, bool) or not isinstance(angle_deg, (int, float)):
        return _failure(RotateError("INVALID_ARGUMENT", "angle_deg must be a number"))
    if center_x is None:
        center_x_value = float(0.0)
    elif isinstance(center_x, bool) or not isinstance(center_x, (int, float)):
        return _failure(RotateError("INVALID_ARGUMENT", "center_x must be a number"))
    else:
        center_x_value = float(center_x)
    if center_y is None:
        center_y_value = float(0.0)
    elif isinstance(center_y, bool) or not isinstance(center_y, (int, float)):
        return _failure(RotateError("INVALID_ARGUMENT", "center_y must be a number"))
    else:
        center_y_value = float(center_y)
    if center_z is None:
        center_z_value = float(0.0)
    elif isinstance(center_z, bool) or not isinstance(center_z, (int, float)):
        return _failure(RotateError("INVALID_ARGUMENT", "center_z must be a number"))
    else:
        center_z_value = float(center_z)
    request = RotateRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name),
        axis_x=float(axis_x),
        axis_y=float(axis_y),
        axis_z=float(axis_z),
        angle_deg=float(angle_deg),
        center_x=center_x_value,
        center_y=center_y_value,
        center_z=center_z_value
    )
    return request


@dataclass(slots=True)
class _RotateExecution:
    collaborators: RotateCollaborators
    request: RotateRequest
    created: RotateReceipt | None = None
    inspected: RotateInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_rotate(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise RotateError(
                "INVALID_ROTATE_RESULT",
                "rotate did not return an identity receipt",
            )
        self.inspected = read_rotate_result(doc, self.created, self.request)

    def run(self) -> RotateResult:
        result = run_rotate_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_rotate_uncertain(
                "ROTATE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected rotate result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_rotate_success(
            object=as_str(payload["object"]), label=as_str(payload["label"])
        )


def _snapshot_placement(obj: object) -> dict[str, object]:
    placement = getattr(obj, "Placement", None)
    if placement is None:
        raise RotateError("CREATED_OBJECT_INVALID", "Object has no Placement after apply")
    base = getattr(placement, "Base", None)
    if base is None:
        raise RotateError("CREATED_OBJECT_INVALID", "Object Placement has no Base after apply")
    rotation = getattr(placement, "Rotation", None)
    axis = getattr(rotation, "Axis", None) if rotation is not None else None
    if rotation is None or axis is None:
        raise RotateError("CREATED_OBJECT_INVALID", "Object Placement has no Rotation after apply")
    return {
        "base": {
            "x": as_float(getattr(base, "x", 0.0)),
            "y": as_float(getattr(base, "y", 0.0)),
            "z": as_float(getattr(base, "z", 0.0)),
        },
        "rotation_axis": {
            "x": as_float(getattr(axis, "x", 0.0)),
            "y": as_float(getattr(axis, "y", 0.0)),
            "z": as_float(getattr(axis, "z", 0.0)),
        },
        "rotation_angle": as_float(getattr(rotation, "Angle", 0.0)),
    }


def _placement_matches(obj: object, expected: dict[str, object]) -> None:
    placement = getattr(obj, "Placement", None)
    if placement is None:
        raise RotateError("CREATED_OBJECT_INVALID", "Object has no Placement after recompute")
    base = getattr(placement, "Base", None)
    rotation = getattr(placement, "Rotation", None)
    axis = getattr(rotation, "Axis", None) if rotation is not None else None
    if base is None or rotation is None or axis is None:
        raise RotateError("CREATED_OBJECT_INVALID", "Object Placement is incomplete after recompute")
    expected_base = expected["base"]
    if not isinstance(expected_base, dict):
        raise RotateError("CREATED_OBJECT_INVALID", "Missing post-apply Placement snapshot")
    for key in ("x", "y", "z"):
        actual = as_float(getattr(base, key, 0.0))
        target = as_float(expected_base[key])
        if abs(actual - target) > 1e-6:
            raise RotateError(
                "CREATED_OBJECT_INVALID",
                f"Placement Base {key} mismatch after recompute",
            )
    expected_axis = expected["rotation_axis"]
    if not isinstance(expected_axis, dict):
        raise RotateError("CREATED_OBJECT_INVALID", "Missing post-apply Placement snapshot")
    for key in ("x", "y", "z"):
        actual = as_float(getattr(axis, key, 0.0))
        target = as_float(expected_axis[key])
        if abs(actual - target) > 1e-6:
            raise RotateError(
                "CREATED_OBJECT_INVALID",
                f"Placement Rotation axis {key} mismatch after recompute",
            )
    actual_angle = as_float(getattr(rotation, "Angle", 0.0))
    target_angle = as_float(expected["rotation_angle"])
    if abs(actual_angle - target_angle) > 1e-6:
        raise RotateError("CREATED_OBJECT_INVALID", "Placement Rotation angle mismatch after recompute")


def apply_rotate(doc: MutationDocument, request: RotateRequest) -> RotateReceipt:
    """Apply rotate without recomputing or managing a transaction."""

    payload = measure_io_actions.rotate(doc, request.obj_name, axis_x=request.axis_x, axis_y=request.axis_y, axis_z=request.axis_z, angle_deg=request.angle_deg, center_x=request.center_x, center_y=request.center_y, center_z=request.center_z)
    target = payload.get("object")
    found = doc.getObject(str(target)) if isinstance(target, str) else None
    expected = _snapshot_placement(found) if found is not None else None
    return RotateReceipt(payload=dict(payload), obj=found, expected=expected)



def read_rotate_result(
    doc: MutationReadDocument, receipt: RotateReceipt, request: RotateRequest
) -> RotateInspection:
    key = "object"
    name = receipt.payload.get(key)
    if not isinstance(name, str) or not name.strip():
        raise RotateError("INVALID_ROTATE_RESULT", "missing created identity")
    obj = doc.getObject(name)
    if obj is None:
        raise RotateError("CREATED_OBJECT_MISSING", f"Created object is missing: {name!r}")
    if receipt.obj is not None and obj is not receipt.obj:
        raise RotateError("CREATED_OBJECT_REPLACED", f"Created object was replaced: {name!r}")
    if receipt.expected is None:
        raise RotateError("CREATED_OBJECT_INVALID", "Missing post-apply Placement snapshot")
    _placement_matches(obj, receipt.expected)

    payload = dict(receipt.payload)
    if hasattr(obj, "Label") and "label" in payload:
        payload["label"] = str(obj.Label)
    return RotateInspection(payload=payload)



def run_rotate(
    collaborators: RotateCollaborators,
    doc_name: str, obj_name: str, axis_x: float, axis_y: float, axis_z: float, angle_deg: float, center_x: float = 0.0, center_y: float = 0.0, center_z: float = 0.0,
) -> RotateResult:
    """Run rotate through apply, recompute, inspection, and commit."""

    request = build_rotate_request(doc_name, obj_name, axis_x, axis_y, axis_z, angle_deg, center_x, center_y, center_z)
    if isinstance(request, dict):
        return request
    return _RotateExecution(collaborators, request).run()


class _RotateRpcFacade(Protocol):
    _cad_collaborators: RotateCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_rotate(
    self: _RotateRpcFacade,
    doc_name: str, obj_name: str, axis_x: float, axis_y: float, axis_z: float, angle_deg: float, center_x: float = 0.0, center_y: float = 0.0, center_z: float = 0.0,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_rotate(collaborators, doc_name, obj_name, axis_x, axis_y, axis_z, angle_deg, center_x, center_y, center_z)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("rotate", rpc_rotate)


__all__ = [
    "RotateCollaborators",
    "RotateError",
    "RotateInspection",
    "RotateReceipt",
    "apply_rotate",
    "build_rotate_request",
    "read_rotate_result",
    "rpc_rotate",
    "run_rotate",
    "TYPED_RPC_HANDLER",
]
