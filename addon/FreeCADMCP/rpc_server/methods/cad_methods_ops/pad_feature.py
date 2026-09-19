"""Typed ``pad_feature`` mutation."""

from __future__ import annotations

import math

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.pad_feature_contract import (
        DocumentName,
        PadFeatureCollaborators,
        PadFeatureDocument,
        PadFeatureFailure,
        PadFeatureObject,
        PadFeatureReadDocument,
        PadFeatureResult,
        PadName,
        make_pad_feature_failure,
        make_pad_feature_success,
        make_pad_feature_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.pad_feature_contract import (
        DocumentName,
        PadFeatureCollaborators,
        PadFeatureDocument,
        PadFeatureFailure,
        PadFeatureObject,
        PadFeatureReadDocument,
        PadFeatureResult,
        PadName,
        make_pad_feature_failure,
        make_pad_feature_success,
        make_pad_feature_uncertain,
    )
from .profile_checks import self_intersecting_wire_numbers, solid_result_issue
from .pad_feature_mutation import PadFeatureError, run_pad_feature_native_mutation


@dataclass(frozen=True, slots=True)
class PadFeatureReceipt:
    name: str
    pad: PadFeatureObject
    body_name: str
    sketch_name: str
    expected_length: float


@dataclass(frozen=True, slots=True)
class PadFeatureInspection:
    name: PadName
    label: str


@dataclass(frozen=True, slots=True, kw_only=True)
class _PadFeatureRequest:
    doc_name: DocumentName
    sketch_name: str
    pad_name: PadName
    length: float
    body_name: str | None
    symmetric: bool
    reversed_dir: bool
    strict: bool


def _failure(error: PadFeatureError, *, retry_safe: bool = True) -> PadFeatureFailure:
    return make_pad_feature_failure(
        error.code,
        str(error),
        retry_safe=retry_safe,
        diagnostics=error.diagnostics,
    )


def _is_type(obj: object, type_id: str) -> bool:
    derived = getattr(obj, "isDerivedFrom", None)
    if callable(derived):
        try:
            return bool(derived(type_id))
        except (AttributeError, TypeError):
            pass
    return getattr(obj, "TypeId", None) == type_id


def _resolve_body(doc: PadFeatureDocument, sketch: object, body_name: str | None) -> object:
    if body_name is not None:
        body = doc.getObject(body_name)
        if body is None:
            raise PadFeatureError("BODY_NOT_FOUND", f"Body {body_name!r} not found")
        if not _is_type(body, "PartDesign::Body"):
            raise PadFeatureError(
                "BODY_WRONG_TYPE",
                f"Object is not a PartDesign::Body: {body_name!r}",
            )
        return body
    for obj in getattr(doc, "Objects", ()):
        if _is_type(obj, "PartDesign::Body") and sketch in getattr(obj, "Group", ()):
            return obj
    raise PadFeatureError(
        "BODY_NOT_FOUND",
        "No PartDesign::Body found to own the pad; create a Body first",
    )


def _profile_diagnostics(sketch: object) -> dict[str, object]:
    diagnostics: dict[str, object] = {
        "conflicting": list(getattr(sketch, "ConflictingConstraints", []) or []),
        "redundant": list(getattr(sketch, "RedundantConstraints", []) or []),
        "malformed": list(getattr(sketch, "MalformedConstraints", []) or []),
        "solver_message": getattr(sketch, "SolverMessage", None),
        "is_closed": None,
    }
    try:
        shape = getattr(sketch, "Shape", None)
        is_null = getattr(shape, "isNull", None) if shape is not None else None
        if shape is not None and not (callable(is_null) and is_null()):
            diagnostics["is_closed"] = bool(shape.isClosed())
    except Exception:
        pass
    return diagnostics


def _require_closed_profile(sketch: object, sketch_name: str, *, part: object = None) -> None:
    diagnostics = _profile_diagnostics(sketch)
    if (
        diagnostics["conflicting"]
        or diagnostics["malformed"]
        or diagnostics["is_closed"] is not True
    ):
        raise PadFeatureError(
            "SKETCH_PROFILE_NOT_CLOSED",
            "Sketch profile is not pad-ready",
            diagnostics=diagnostics,
        )
    crossing = self_intersecting_wire_numbers(getattr(sketch, "Shape", None), part)
    if crossing:
        raise PadFeatureError(
            "SKETCH_PROFILE_SELF_INTERSECTING",
            f"Sketch {sketch_name!r} profile wire(s) {crossing} intersect themselves",
            diagnostics=diagnostics,
        )


def _extrusion_length(feature: object, feature_name: str) -> float:
    length = getattr(feature, "Length", None)
    if length is None:
        raise PadFeatureError(
            "PAD_LENGTH_MISMATCH",
            f"Pad {feature_name!r} has no Length after recompute",
        )
    value = getattr(length, "Value", length)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PadFeatureError(
            "PAD_LENGTH_MISMATCH",
            f"Pad {feature_name!r} Length is not numeric after recompute",
        )
    return float(value)


def _profile_sketch(profile: object) -> object | None:
    if isinstance(profile, (list, tuple)) and profile:
        first: object = profile[0]
        return first
    return profile


def apply_pad_feature(
    doc: PadFeatureDocument,
    sketch_name: str,
    pad_name: PadName,
    length: float,
    body_name: str | None,
    symmetric: bool,
    reversed_dir: bool,
    collaborators: PadFeatureCollaborators,
) -> PadFeatureReceipt:
    """Create a Pad without recomputing or managing a transaction."""

    if doc.getObject(pad_name) is not None:
        raise PadFeatureError("OBJECT_ALREADY_EXISTS", f"Object already exists: {pad_name!r}")
    sketch = doc.getObject(sketch_name)
    if sketch is None:
        raise PadFeatureError("SKETCH_NOT_FOUND", f"Sketch {sketch_name!r} not found")
    if not _is_type(sketch, "Sketcher::SketchObject"):
        raise PadFeatureError("NOT_A_SKETCH", f"Object {sketch_name!r} is not a sketch")
    _require_closed_profile(sketch, sketch_name, part=getattr(collaborators, "part", None))
    body = _resolve_body(doc, sketch, body_name)
    new_object = getattr(body, "newObject", None)
    if not callable(new_object):
        raise PadFeatureError("BODY_WRONG_TYPE", "Body cannot create a Pad")
    pad = new_object("PartDesign::Pad", pad_name)
    pad.Profile = (sketch, [""])
    pad.Length = length
    collaborators.set_extrusion_symmetric(pad, symmetric)
    collaborators.set_feature_bool(pad, ("Reversed",), reversed_dir)
    body.Tip = pad  # type: ignore[attr-defined]
    return PadFeatureReceipt(
        name=pad.Name,
        pad=pad,
        body_name=str(getattr(body, "Name", "")),
        sketch_name=sketch.Name,
        expected_length=length,
    )


def read_pad_feature_result(
    doc: PadFeatureReadDocument, receipt: PadFeatureReceipt
) -> PadFeatureInspection:
    pad = doc.getObject(receipt.name)
    if pad is None:
        raise PadFeatureError("CREATED_OBJECT_MISSING", f"Created pad is missing: {receipt.name!r}")
    if pad is not receipt.pad:
        raise PadFeatureError(
            "CREATED_OBJECT_REPLACED",
            f"Created pad was replaced before commit: {receipt.name!r}",
        )
    if not _is_type(pad, "PartDesign::Pad"):
        raise PadFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not a PartDesign::Pad: {receipt.name!r}",
        )
    body = doc.getObject(receipt.body_name)
    if body is None or pad not in getattr(body, "Group", ()):
        raise PadFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Pad {receipt.name!r} is not a member of Body {receipt.body_name!r}",
        )
    if getattr(body, "Tip", None) is not pad:
        raise PadFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Body {receipt.body_name!r} Tip did not advance to {receipt.name!r}",
        )
    sketch = doc.getObject(receipt.sketch_name)
    profile_sketch = _profile_sketch(getattr(pad, "Profile", None))
    if sketch is None or profile_sketch is not sketch:
        raise PadFeatureError(
            "PAD_PROFILE_MISMATCH",
            f"Pad {receipt.name!r} Profile does not reference sketch {receipt.sketch_name!r}",
        )
    actual_length = _extrusion_length(pad, receipt.name)
    if abs(actual_length - receipt.expected_length) > 1e-6:
        raise PadFeatureError(
            "PAD_LENGTH_MISMATCH",
            f"Pad {receipt.name!r} Length {actual_length} does not match {receipt.expected_length}",
        )
    issue = solid_result_issue(getattr(pad, "Shape", None))
    if issue is not None:
        raise PadFeatureError(
            "PAD_SHAPE_EMPTY",
            f"Pad {receipt.name!r} {issue} after recompute",
        )
    return PadFeatureInspection(name=PadName(receipt.name), label=str(receipt.pad.Label))


def build_pad_feature_request(
    doc_name: object,
    sketch_name: object,
    pad_name: object,
    length: object,
    body_name: object,
    symmetric: object,
    reversed_dir: object,
    strict: object = False,
) -> _PadFeatureRequest | PadFeatureFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(PadFeatureError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(sketch_name, str) or not sketch_name.strip():
        return _failure(PadFeatureError("INVALID_ARGUMENT", "sketch_name must be a nonempty string"))
    if not isinstance(pad_name, str) or not pad_name.strip():
        return _failure(PadFeatureError("INVALID_ARGUMENT", "pad_name must be a nonempty string"))
    if isinstance(length, bool) or not isinstance(length, (int, float)):
        return _failure(PadFeatureError("INVALID_ARGUMENT", "length must be a number"))
    if not math.isfinite(float(length)) or float(length) <= 0:
        return _failure(PadFeatureError("INVALID_ARGUMENT", "length must be a finite number greater than zero"))
    if body_name is not None and (not isinstance(body_name, str) or not body_name.strip()):
        return _failure(PadFeatureError("INVALID_ARGUMENT", "body_name must be a nonempty string"))
    if not isinstance(symmetric, bool):
        return _failure(PadFeatureError("INVALID_ARGUMENT", "symmetric must be a boolean"))
    if not isinstance(reversed_dir, bool):
        return _failure(PadFeatureError("INVALID_ARGUMENT", "reversed_dir must be a boolean"))
    if not isinstance(strict, bool):
        return _failure(PadFeatureError("INVALID_ARGUMENT", "strict must be a boolean"))
    if strict and not body_name:
        return _failure(
            PadFeatureError(
                "INVALID_ARGUMENT",
                f"strict PartDesign mode requires an explicit body_name for pad {pad_name!r}",
            )
        )
    return _PadFeatureRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=sketch_name,
        pad_name=PadName(pad_name),
        length=float(length),
        body_name=body_name,
        symmetric=symmetric,
        reversed_dir=reversed_dir,
        strict=strict,
    )


@dataclass(slots=True)
class _PadFeatureExecution:
    collaborators: PadFeatureCollaborators
    request: _PadFeatureRequest
    created: PadFeatureReceipt | None = None
    inspected: PadFeatureInspection | None = None

    def apply(self, doc: PadFeatureDocument) -> None:
        self.created = apply_pad_feature(
            doc,
            self.request.sketch_name,
            self.request.pad_name,
            self.request.length,
            self.request.body_name,
            self.request.symmetric,
            self.request.reversed_dir,
            self.collaborators,
        )

    def inspect(self, doc: PadFeatureReadDocument) -> None:
        if self.created is None:
            raise PadFeatureError(
                "INVALID_PAD_FEATURE_RESULT",
                "Pad creation did not return an identity receipt",
            )
        self.inspected = read_pad_feature_result(doc, self.created)

    def run(self) -> PadFeatureResult:
        result = run_pad_feature_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_pad_feature_uncertain(
                "PAD_FEATURE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected Pad result",
                committed=True,
            )
        return make_pad_feature_success(self.inspected.name, self.inspected.label)


def run_pad_feature(
    collaborators: PadFeatureCollaborators,
    doc_name: object,
    sketch_name: object,
    pad_name: object,
    length: object,
    body_name: object = None,
    symmetric: object = False,
    reversed_dir: object = False,
    strict: object = False,
) -> PadFeatureResult:
    request = build_pad_feature_request(
        doc_name, sketch_name, pad_name, length, body_name, symmetric, reversed_dir, strict
    )
    if isinstance(request, dict):
        return request
    return _PadFeatureExecution(collaborators, request).run()


class _PadFeatureRpcFacade(Protocol):
    _cad_collaborators: PadFeatureCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_pad_feature(
    self: _PadFeatureRpcFacade,
    doc_name: str,
    sketch_name: str,
    pad_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
    strict: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_pad_feature(
            collaborators,
            doc_name,
            sketch_name,
            pad_name,
            length,
            body_name,
            symmetric,
            reversed_dir,
            strict,
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("pad_feature", rpc_pad_feature)


__all__ = [
    "PadFeatureCollaborators",
    "PadFeatureError",
    "PadFeatureInspection",
    "PadFeatureReceipt",
    "apply_pad_feature",
    "build_pad_feature_request",
    "read_pad_feature_result",
    "rpc_pad_feature",
    "run_pad_feature",
    "TYPED_RPC_HANDLER",
]
