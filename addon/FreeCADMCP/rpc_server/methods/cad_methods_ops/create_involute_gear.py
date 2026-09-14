"""Typed ``create_involute_gear`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.create_involute_gear_contract import (
    GearName,
    DocumentName,
    CreateInvoluteGearCollaborators,
    CreateInvoluteGearFailure,
    CreateInvoluteGearRequest,
    CreateInvoluteGearResult,
    MutationDocument,
    MutationObject,
    MutationReadDocument,
    make_create_involute_gear_failure,
    make_create_involute_gear_success,
    make_create_involute_gear_uncertain,
)
from .typed_runtime import as_float, as_int, as_str
from . import gear_actions
from .create_involute_gear_mutation import CreateInvoluteGearError, run_create_involute_gear_native_mutation


@dataclass(frozen=True, slots=True)
class CreateInvoluteGearReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class CreateInvoluteGearInspection:
    payload: dict[str, object]


def _failure(error: CreateInvoluteGearError, *, retry_safe: bool = True) -> CreateInvoluteGearFailure:
    return make_create_involute_gear_failure(error.code, str(error), retry_safe=retry_safe)


def build_create_involute_gear_request(
    doc_name: object, gear_name: object, teeth: object, module: object, width: object, pressure_angle: object, bore_diameter: object, clearance: object, backlash: object, samples_per_flank: object, body_name: object, sketch_name: object
) -> CreateInvoluteGearRequest | CreateInvoluteGearFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(CreateInvoluteGearError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(gear_name, str) or not gear_name.strip():
        return _failure(CreateInvoluteGearError("INVALID_ARGUMENT", "gear_name must be a nonempty string"))
    if isinstance(teeth, bool) or not isinstance(teeth, int):
        return _failure(CreateInvoluteGearError("INVALID_ARGUMENT", "teeth must be an integer"))
    if isinstance(module, bool) or not isinstance(module, (int, float)):
        return _failure(CreateInvoluteGearError("INVALID_ARGUMENT", "module must be a number"))
    if isinstance(width, bool) or not isinstance(width, (int, float)):
        return _failure(CreateInvoluteGearError("INVALID_ARGUMENT", "width must be a number"))
    if pressure_angle is None:
        pressure_angle_value = float(20.0)
    elif isinstance(pressure_angle, bool) or not isinstance(pressure_angle, (int, float)):
        return _failure(CreateInvoluteGearError("INVALID_ARGUMENT", "pressure_angle must be a number"))
    else:
        pressure_angle_value = float(pressure_angle)
    if bore_diameter is None:
        bore_diameter_value = float(0.0)
    elif isinstance(bore_diameter, bool) or not isinstance(bore_diameter, (int, float)):
        return _failure(CreateInvoluteGearError("INVALID_ARGUMENT", "bore_diameter must be a number"))
    else:
        bore_diameter_value = float(bore_diameter)
    if clearance is None:
        clearance_value = float(0.0)
    elif isinstance(clearance, bool) or not isinstance(clearance, (int, float)):
        return _failure(CreateInvoluteGearError("INVALID_ARGUMENT", "clearance must be a number"))
    else:
        clearance_value = float(clearance)
    if backlash is None:
        backlash_value = float(0.0)
    elif isinstance(backlash, bool) or not isinstance(backlash, (int, float)):
        return _failure(CreateInvoluteGearError("INVALID_ARGUMENT", "backlash must be a number"))
    else:
        backlash_value = float(backlash)
    if samples_per_flank is None:
        samples_per_flank_value = 12
    elif isinstance(samples_per_flank, bool) or not isinstance(samples_per_flank, int):
        return _failure(CreateInvoluteGearError("INVALID_ARGUMENT", "samples_per_flank must be an integer"))
    else:
        samples_per_flank_value = samples_per_flank
    if body_name is None:
        body_name_value: str | None = None
    elif not isinstance(body_name, str):
        return _failure(CreateInvoluteGearError("INVALID_ARGUMENT", "body_name must be a string or null"))
    else:
        body_name_value = body_name
    if sketch_name is None:
        sketch_name_value: str | None = None
    elif not isinstance(sketch_name, str):
        return _failure(CreateInvoluteGearError("INVALID_ARGUMENT", "sketch_name must be a string or null"))
    else:
        sketch_name_value = sketch_name
    request = CreateInvoluteGearRequest(
        doc_name=DocumentName(doc_name),
        gear_name=GearName(gear_name),
        teeth=teeth,
        module=float(module),
        width=float(width),
        pressure_angle=pressure_angle_value,
        bore_diameter=bore_diameter_value,
        clearance=clearance_value,
        backlash=backlash_value,
        samples_per_flank=samples_per_flank_value,
        body_name=body_name_value,
        sketch_name=sketch_name_value
    )
    return request


@dataclass(slots=True)
class _CreateInvoluteGearExecution:
    collaborators: CreateInvoluteGearCollaborators
    request: CreateInvoluteGearRequest
    created: CreateInvoluteGearReceipt | None = None
    inspected: CreateInvoluteGearInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_create_involute_gear(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise CreateInvoluteGearError(
                "INVALID_CREATE_INVOLUTE_GEAR_RESULT",
                "create_involute_gear did not return an identity receipt",
            )
        self.inspected = read_create_involute_gear_result(doc, self.created, self.request)

    def run(self) -> CreateInvoluteGearResult:
        result = run_create_involute_gear_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_create_involute_gear_uncertain(
                "CREATE_INVOLUTE_GEAR_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected create_involute_gear result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_create_involute_gear_success(
            body=as_str(payload["body"]), sketch=as_str(payload["sketch"]), feature=as_str(payload["feature"]), teeth=as_int(payload["teeth"]), module=as_float(payload["module"])
        )


def apply_create_involute_gear(doc: MutationDocument, request: CreateInvoluteGearRequest) -> CreateInvoluteGearReceipt:
    """Apply create_involute_gear without recomputing or managing a transaction."""

    receipt = gear_actions.create_involute_gear(doc, gear_name=request.gear_name, teeth=request.teeth, module=request.module, width=request.width, pressure_angle=request.pressure_angle, bore_diameter=request.bore_diameter, clearance=request.clearance, backlash=request.backlash, samples_per_flank=request.samples_per_flank, body_name=request.body_name, sketch_name=request.sketch_name)
    payload = {
        "body": receipt["body"],
        "sketch": receipt["sketch"],
        "feature": receipt["feature"],
        "teeth": receipt["teeth"],
        "module": receipt["module"],
    }
    feature = payload["feature"]
    found = doc.getObject(str(feature)) if isinstance(feature, str) else None
    return CreateInvoluteGearReceipt(payload=payload, obj=found)



def read_create_involute_gear_result(
    doc: MutationReadDocument, receipt: CreateInvoluteGearReceipt, request: CreateInvoluteGearRequest
) -> CreateInvoluteGearInspection:
    key = "feature"
    name = receipt.payload.get(key)
    if not isinstance(name, str) or not name.strip():
        raise CreateInvoluteGearError("INVALID_CREATE_INVOLUTE_GEAR_RESULT", "missing created identity")
    obj = doc.getObject(name)
    if obj is None:
        raise CreateInvoluteGearError("CREATED_OBJECT_MISSING", f"Created object is missing: {name!r}")
    if receipt.obj is not None and obj is not receipt.obj:
        raise CreateInvoluteGearError("CREATED_OBJECT_REPLACED", f"Created object was replaced: {name!r}")

    payload = dict(receipt.payload)
    if hasattr(obj, "Label") and "label" in payload:
        payload["label"] = str(obj.Label)
    return CreateInvoluteGearInspection(payload=payload)



def run_create_involute_gear(
    collaborators: CreateInvoluteGearCollaborators,
    doc_name: str, gear_name: str, teeth: int, module: float, width: float, pressure_angle: float = 20.0, bore_diameter: float = 0.0, clearance: float = 0.0, backlash: float = 0.0, samples_per_flank: int = 12, body_name: str | None = None, sketch_name: str | None = None,
) -> CreateInvoluteGearResult:
    """Run create_involute_gear through apply, recompute, inspection, and commit."""

    request = build_create_involute_gear_request(doc_name, gear_name, teeth, module, width, pressure_angle, bore_diameter, clearance, backlash, samples_per_flank, body_name, sketch_name)
    if isinstance(request, dict):
        return request
    return _CreateInvoluteGearExecution(collaborators, request).run()


class _CreateInvoluteGearRpcFacade(Protocol):
    _cad_collaborators: CreateInvoluteGearCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_create_involute_gear(
    self: _CreateInvoluteGearRpcFacade,
    doc_name: str, gear_name: str, teeth: int, module: float, width: float, pressure_angle: float = 20.0, bore_diameter: float = 0.0, clearance: float = 0.0, backlash: float = 0.0, samples_per_flank: int = 12, body_name: str | None = None, sketch_name: str | None = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_create_involute_gear(collaborators, doc_name, gear_name, teeth, module, width, pressure_angle, bore_diameter, clearance, backlash, samples_per_flank, body_name, sketch_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("create_involute_gear", rpc_create_involute_gear)


__all__ = [
    "CreateInvoluteGearCollaborators",
    "CreateInvoluteGearError",
    "CreateInvoluteGearInspection",
    "CreateInvoluteGearReceipt",
    "apply_create_involute_gear",
    "build_create_involute_gear_request",
    "read_create_involute_gear_result",
    "rpc_create_involute_gear",
    "run_create_involute_gear",
    "TYPED_RPC_HANDLER",
]
