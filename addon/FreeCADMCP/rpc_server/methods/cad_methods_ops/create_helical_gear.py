"""Typed ``create_helical_gear`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.create_helical_gear_contract import (
    GearName,
    DocumentName,
    CreateHelicalGearCollaborators,
    CreateHelicalGearFailure,
    CreateHelicalGearRequest,
    CreateHelicalGearResult,
    MutationDocument,
    MutationObject,
    MutationReadDocument,
    make_create_helical_gear_failure,
    make_create_helical_gear_success,
    make_create_helical_gear_uncertain,
)
from .typed_runtime import TypedMutationError, as_float, as_int, as_str
from . import gear_actions
from .create_helical_gear_mutation import CreateHelicalGearError, run_create_helical_gear_native_mutation


@dataclass(frozen=True, slots=True)
class CreateHelicalGearReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class CreateHelicalGearInspection:
    payload: dict[str, object]


def _failure(error: CreateHelicalGearError, *, retry_safe: bool = True) -> CreateHelicalGearFailure:
    return make_create_helical_gear_failure(error.code, str(error), retry_safe=retry_safe)


def build_create_helical_gear_request(
    doc_name: object, gear_name: object, teeth: object, module: object, width: object, helix_angle: object, pressure_angle: object, bore_diameter: object, clearance: object, backlash: object, samples_per_flank: object, body_name: object
) -> CreateHelicalGearRequest | CreateHelicalGearFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(CreateHelicalGearError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(gear_name, str) or not gear_name.strip():
        return _failure(CreateHelicalGearError("INVALID_ARGUMENT", "gear_name must be a nonempty string"))
    if isinstance(teeth, bool) or not isinstance(teeth, int):
        return _failure(CreateHelicalGearError("INVALID_ARGUMENT", "teeth must be an integer"))
    if isinstance(module, bool) or not isinstance(module, (int, float)):
        return _failure(CreateHelicalGearError("INVALID_ARGUMENT", "module must be a number"))
    if isinstance(width, bool) or not isinstance(width, (int, float)):
        return _failure(CreateHelicalGearError("INVALID_ARGUMENT", "width must be a number"))
    if helix_angle is None:
        helix_angle_value = float(15.0)
    elif isinstance(helix_angle, bool) or not isinstance(helix_angle, (int, float)):
        return _failure(CreateHelicalGearError("INVALID_ARGUMENT", "helix_angle must be a number"))
    else:
        helix_angle_value = float(helix_angle)
    if pressure_angle is None:
        pressure_angle_value = float(20.0)
    elif isinstance(pressure_angle, bool) or not isinstance(pressure_angle, (int, float)):
        return _failure(CreateHelicalGearError("INVALID_ARGUMENT", "pressure_angle must be a number"))
    else:
        pressure_angle_value = float(pressure_angle)
    if bore_diameter is None:
        bore_diameter_value = float(0.0)
    elif isinstance(bore_diameter, bool) or not isinstance(bore_diameter, (int, float)):
        return _failure(CreateHelicalGearError("INVALID_ARGUMENT", "bore_diameter must be a number"))
    else:
        bore_diameter_value = float(bore_diameter)
    if clearance is None:
        clearance_value = float(0.0)
    elif isinstance(clearance, bool) or not isinstance(clearance, (int, float)):
        return _failure(CreateHelicalGearError("INVALID_ARGUMENT", "clearance must be a number"))
    else:
        clearance_value = float(clearance)
    if backlash is None:
        backlash_value = float(0.0)
    elif isinstance(backlash, bool) or not isinstance(backlash, (int, float)):
        return _failure(CreateHelicalGearError("INVALID_ARGUMENT", "backlash must be a number"))
    else:
        backlash_value = float(backlash)
    if samples_per_flank is None:
        samples_per_flank_value = 12
    elif isinstance(samples_per_flank, bool) or not isinstance(samples_per_flank, int):
        return _failure(CreateHelicalGearError("INVALID_ARGUMENT", "samples_per_flank must be an integer"))
    else:
        samples_per_flank_value = samples_per_flank
    if body_name is None:
        body_name_value: str | None = None
    elif not isinstance(body_name, str):
        return _failure(CreateHelicalGearError("INVALID_ARGUMENT", "body_name must be a string or null"))
    else:
        body_name_value = body_name
    request = CreateHelicalGearRequest(
        doc_name=DocumentName(doc_name),
        gear_name=GearName(gear_name),
        teeth=teeth,
        module=float(module),
        width=float(width),
        helix_angle=helix_angle_value,
        pressure_angle=pressure_angle_value,
        bore_diameter=bore_diameter_value,
        clearance=clearance_value,
        backlash=backlash_value,
        samples_per_flank=samples_per_flank_value,
        body_name=body_name_value
    )
    return request


@dataclass(slots=True)
class _CreateHelicalGearExecution:
    collaborators: CreateHelicalGearCollaborators
    request: CreateHelicalGearRequest
    created: CreateHelicalGearReceipt | None = None
    inspected: CreateHelicalGearInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_create_helical_gear(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise CreateHelicalGearError(
                "INVALID_CREATE_HELICAL_GEAR_RESULT",
                "create_helical_gear did not return an identity receipt",
            )
        self.inspected = read_create_helical_gear_result(doc, self.created, self.request)

    def run(self) -> CreateHelicalGearResult:
        result = run_create_helical_gear_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_create_helical_gear_uncertain(
                "CREATE_HELICAL_GEAR_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected create_helical_gear result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_create_helical_gear_success(
            body=as_str(payload["body"]), sketch=as_str(payload["sketch"]), feature=as_str(payload["feature"]), teeth=as_int(payload["teeth"]), module=as_float(payload["module"])
        )


def apply_create_helical_gear(doc: MutationDocument, request: CreateHelicalGearRequest) -> CreateHelicalGearReceipt:
    """Apply create_helical_gear without recomputing or managing a transaction."""

    receipt = gear_actions.create_helical_gear(doc, gear_name=request.gear_name, teeth=request.teeth, module=request.module, width=request.width, helix_angle=request.helix_angle, pressure_angle=request.pressure_angle, bore_diameter=request.bore_diameter, clearance=request.clearance, backlash=request.backlash, samples_per_flank=request.samples_per_flank, body_name=request.body_name)
    payload = {
        "body": receipt["body"],
        "sketch": receipt["sketch"],
        "feature": receipt["feature"],
        "teeth": receipt["teeth"],
        "module": receipt["module"],
    }
    feature = payload["feature"]
    found = doc.getObject(str(feature)) if isinstance(feature, str) else None
    return CreateHelicalGearReceipt(payload=payload, obj=found)



def read_create_helical_gear_result(
    doc: MutationReadDocument, receipt: CreateHelicalGearReceipt, request: CreateHelicalGearRequest
) -> CreateHelicalGearInspection:
    key = "feature"
    name = receipt.payload.get(key)
    if not isinstance(name, str) or not name.strip():
        raise CreateHelicalGearError("INVALID_CREATE_HELICAL_GEAR_RESULT", "missing created identity")
    obj = doc.getObject(name)
    if obj is None:
        raise CreateHelicalGearError("CREATED_OBJECT_MISSING", f"Created object is missing: {name!r}")
    if receipt.obj is not None and obj is not receipt.obj:
        raise CreateHelicalGearError("CREATED_OBJECT_REPLACED", f"Created object was replaced: {name!r}")

    body_name = receipt.payload.get("body")
    sketch_name = receipt.payload.get("sketch")
    if not isinstance(body_name, str) or not isinstance(sketch_name, str):
        raise CreateHelicalGearError("INVALID_CREATE_HELICAL_GEAR_RESULT", "missing created identity")
    try:
        gear_actions.inspect_created_gear(
            doc,
            body_name=body_name,
            sketch_name=sketch_name,
            feature_name=name,
            feature=obj,
            width=request.width,
            helical=True,
        )
    except TypedMutationError as exc:
        raise CreateHelicalGearError(exc.code, str(exc)) from exc
    payload = dict(receipt.payload)
    if hasattr(obj, "Label") and "label" in payload:
        payload["label"] = str(obj.Label)
    return CreateHelicalGearInspection(payload=payload)



def run_create_helical_gear(
    collaborators: CreateHelicalGearCollaborators,
    doc_name: str, gear_name: str, teeth: int, module: float, width: float, helix_angle: float = 15.0, pressure_angle: float = 20.0, bore_diameter: float = 0.0, clearance: float = 0.0, backlash: float = 0.0, samples_per_flank: int = 12, body_name: str | None = None,
) -> CreateHelicalGearResult:
    """Run create_helical_gear through apply, recompute, inspection, and commit."""

    request = build_create_helical_gear_request(doc_name, gear_name, teeth, module, width, helix_angle, pressure_angle, bore_diameter, clearance, backlash, samples_per_flank, body_name)
    if isinstance(request, dict):
        return request
    return _CreateHelicalGearExecution(collaborators, request).run()


class _CreateHelicalGearRpcFacade(Protocol):
    _cad_collaborators: CreateHelicalGearCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_create_helical_gear(
    self: _CreateHelicalGearRpcFacade,
    doc_name: str, gear_name: str, teeth: int, module: float, width: float, helix_angle: float = 15.0, pressure_angle: float = 20.0, bore_diameter: float = 0.0, clearance: float = 0.0, backlash: float = 0.0, samples_per_flank: int = 12, body_name: str | None = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_create_helical_gear(collaborators, doc_name, gear_name, teeth, module, width, helix_angle, pressure_angle, bore_diameter, clearance, backlash, samples_per_flank, body_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("create_helical_gear", rpc_create_helical_gear)


__all__ = [
    "CreateHelicalGearCollaborators",
    "CreateHelicalGearError",
    "CreateHelicalGearInspection",
    "CreateHelicalGearReceipt",
    "apply_create_helical_gear",
    "build_create_helical_gear_request",
    "read_create_helical_gear_result",
    "rpc_create_helical_gear",
    "run_create_helical_gear",
    "TYPED_RPC_HANDLER",
]
