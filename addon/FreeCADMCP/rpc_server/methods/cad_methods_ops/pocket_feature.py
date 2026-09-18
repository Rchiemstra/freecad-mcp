"""Typed ``pocket_feature`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.pocket_feature_contract import (
        DocumentName,
        PocketFeatureCollaborators,
        PocketFeatureDocument,
        PocketFeatureFailure,
        PocketFeatureObject,
        PocketFeatureReadDocument,
        PocketFeatureResult,
        PocketName,
        make_pocket_feature_failure,
        make_pocket_feature_success,
        make_pocket_feature_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.pocket_feature_contract import (
        DocumentName,
        PocketFeatureCollaborators,
        PocketFeatureDocument,
        PocketFeatureFailure,
        PocketFeatureObject,
        PocketFeatureReadDocument,
        PocketFeatureResult,
        PocketName,
        make_pocket_feature_failure,
        make_pocket_feature_success,
        make_pocket_feature_uncertain,
    )
from .pocket_feature_mutation import PocketFeatureError, run_pocket_feature_native_mutation


@dataclass(frozen=True, slots=True)
class PocketFeatureReceipt:
    name: str
    pocket: PocketFeatureObject
    body_name: str
    sketch_name: str
    expected_length: float


@dataclass(frozen=True, slots=True)
class PocketFeatureInspection:
    name: PocketName
    label: str


@dataclass(frozen=True, slots=True, kw_only=True)
class _PocketFeatureRequest:
    doc_name: DocumentName
    sketch_name: str
    pocket_name: PocketName
    length: float
    body_name: str | None
    symmetric: bool
    reversed_dir: bool


def _failure(error: PocketFeatureError, *, retry_safe: bool = True) -> PocketFeatureFailure:
    return make_pocket_feature_failure(error.code, str(error), retry_safe=retry_safe)


def _is_type(obj: object, type_id: str) -> bool:
    derived = getattr(obj, "isDerivedFrom", None)
    if callable(derived):
        try:
            return bool(derived(type_id))
        except (AttributeError, TypeError):
            pass
    return getattr(obj, "TypeId", None) == type_id


def _resolve_body(doc: PocketFeatureDocument, sketch: object, body_name: str | None) -> object:
    if body_name is not None:
        body = doc.getObject(body_name)
        if body is None:
            raise PocketFeatureError("BODY_NOT_FOUND", f"Body {body_name!r} not found")
        if not _is_type(body, "PartDesign::Body"):
            raise PocketFeatureError(
                "BODY_WRONG_TYPE",
                f"Object is not a PartDesign::Body: {body_name!r}",
            )
        return body
    for obj in getattr(doc, "Objects", ()):
        if _is_type(obj, "PartDesign::Body") and sketch in getattr(obj, "Group", ()):
            return obj
    raise PocketFeatureError(
        "BODY_NOT_FOUND",
        "No PartDesign::Body found to own the pocket; create a Body first",
    )


def _require_closed_profile(sketch: object, sketch_name: str) -> None:
    conflicting = list(getattr(sketch, "ConflictingConstraints", []) or [])
    malformed = list(getattr(sketch, "MalformedConstraints", []) or [])
    if conflicting:
        raise PocketFeatureError(
            "SKETCH_CONFLICTING_CONSTRAINTS",
            f"Sketch {sketch_name!r} has conflicting constraints",
        )
    if malformed:
        raise PocketFeatureError(
            "SKETCH_MALFORMED_CONSTRAINTS",
            f"Sketch {sketch_name!r} has malformed constraints",
        )
    shape = getattr(sketch, "Shape", None)
    is_closed = getattr(shape, "isClosed", None) if shape is not None else None
    if callable(is_closed):
        try:
            closed = bool(is_closed())
        except (AttributeError, TypeError, RuntimeError) as exc:
            raise PocketFeatureError(
                "SKETCH_SHAPE_INVALID",
                f"Sketch {sketch_name!r} profile shape is invalid: {exc}",
            ) from exc
        if not closed:
            raise PocketFeatureError(
                "SKETCH_PROFILE_NOT_CLOSED",
                f"Sketch {sketch_name!r} profile is not a closed wire",
            )


def _extrusion_length(feature: object, feature_name: str) -> float:
    length = getattr(feature, "Length", None)
    if length is None:
        raise PocketFeatureError(
            "POCKET_LENGTH_MISMATCH",
            f"Pocket {feature_name!r} has no Length after recompute",
        )
    value = getattr(length, "Value", length)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PocketFeatureError(
            "POCKET_LENGTH_MISMATCH",
            f"Pocket {feature_name!r} Length is not numeric after recompute",
        )
    return float(value)


def _profile_sketch(profile: object) -> object | None:
    if isinstance(profile, (list, tuple)) and profile:
        first: object = profile[0]
        return first
    return profile


def apply_pocket_feature(
    doc: PocketFeatureDocument,
    sketch_name: str,
    pocket_name: PocketName,
    length: float,
    body_name: str | None,
    symmetric: bool,
    reversed_dir: bool,
    collaborators: PocketFeatureCollaborators,
) -> PocketFeatureReceipt:
    """Create a Pocket without recomputing or managing a transaction."""

    if doc.getObject(pocket_name) is not None:
        raise PocketFeatureError("OBJECT_ALREADY_EXISTS", f"Object already exists: {pocket_name!r}")
    sketch = doc.getObject(sketch_name)
    if sketch is None:
        raise PocketFeatureError("SKETCH_NOT_FOUND", f"Sketch {sketch_name!r} not found")
    if not _is_type(sketch, "Sketcher::SketchObject"):
        raise PocketFeatureError("NOT_A_SKETCH", f"Object {sketch_name!r} is not a sketch")
    _require_closed_profile(sketch, sketch_name)
    body = _resolve_body(doc, sketch, body_name)
    new_object = getattr(body, "newObject", None)
    if not callable(new_object):
        raise PocketFeatureError("BODY_WRONG_TYPE", "Body cannot create a Pocket")
    pocket = new_object("PartDesign::Pocket", pocket_name)
    pocket.Profile = (sketch, [""])
    pocket.Length = length
    collaborators.set_extrusion_symmetric(pocket, symmetric)
    collaborators.set_feature_bool(pocket, ("Reversed",), reversed_dir)
    body.Tip = pocket  # type: ignore[attr-defined]
    return PocketFeatureReceipt(
        name=pocket.Name,
        pocket=pocket,
        body_name=str(getattr(body, "Name", "")),
        sketch_name=sketch.Name,
        expected_length=length,
    )


def read_pocket_feature_result(
    doc: PocketFeatureReadDocument, receipt: PocketFeatureReceipt
) -> PocketFeatureInspection:
    pocket = doc.getObject(receipt.name)
    if pocket is None:
        raise PocketFeatureError(
            "CREATED_OBJECT_MISSING",
            f"Created pocket is missing: {receipt.name!r}",
        )
    if pocket is not receipt.pocket:
        raise PocketFeatureError(
            "CREATED_OBJECT_REPLACED",
            f"Created pocket was replaced before commit: {receipt.name!r}",
        )
    if not _is_type(pocket, "PartDesign::Pocket"):
        raise PocketFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not a PartDesign::Pocket: {receipt.name!r}",
        )
    body = doc.getObject(receipt.body_name)
    if body is None or pocket not in getattr(body, "Group", ()):
        raise PocketFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Pocket {receipt.name!r} is not a member of Body {receipt.body_name!r}",
        )
    if getattr(body, "Tip", None) is not pocket:
        raise PocketFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Body {receipt.body_name!r} Tip did not advance to {receipt.name!r}",
        )
    sketch = doc.getObject(receipt.sketch_name)
    profile_sketch = _profile_sketch(getattr(pocket, "Profile", None))
    if sketch is None or profile_sketch is not sketch:
        raise PocketFeatureError(
            "POCKET_PROFILE_MISMATCH",
            f"Pocket {receipt.name!r} Profile does not reference sketch {receipt.sketch_name!r}",
        )
    actual_length = _extrusion_length(pocket, receipt.name)
    if abs(actual_length - receipt.expected_length) > 1e-6:
        raise PocketFeatureError(
            "POCKET_LENGTH_MISMATCH",
            f"Pocket {receipt.name!r} Length {actual_length} does not match {receipt.expected_length}",
        )
    shape = getattr(pocket, "Shape", None)
    if shape is None or bool(getattr(shape, "isNull", lambda: True)()):
        raise PocketFeatureError(
            "POCKET_SHAPE_EMPTY",
            f"Pocket {receipt.name!r} has no solid after recompute",
        )
    return PocketFeatureInspection(name=PocketName(receipt.name), label=str(receipt.pocket.Label))


def build_pocket_feature_request(
    doc_name: object,
    sketch_name: object,
    pocket_name: object,
    length: object,
    body_name: object,
    symmetric: object,
    reversed_dir: object,
) -> _PocketFeatureRequest | PocketFeatureFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(PocketFeatureError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(sketch_name, str) or not sketch_name.strip():
        return _failure(PocketFeatureError("INVALID_ARGUMENT", "sketch_name must be a nonempty string"))
    if not isinstance(pocket_name, str) or not pocket_name.strip():
        return _failure(PocketFeatureError("INVALID_ARGUMENT", "pocket_name must be a nonempty string"))
    if isinstance(length, bool) or not isinstance(length, (int, float)):
        return _failure(PocketFeatureError("INVALID_ARGUMENT", "length must be a number"))
    if float(length) <= 0:
        return _failure(PocketFeatureError("INVALID_ARGUMENT", "length must be greater than zero"))
    if body_name is not None and (not isinstance(body_name, str) or not body_name.strip()):
        return _failure(PocketFeatureError("INVALID_ARGUMENT", "body_name must be a nonempty string"))
    if not isinstance(symmetric, bool):
        return _failure(PocketFeatureError("INVALID_ARGUMENT", "symmetric must be a boolean"))
    if not isinstance(reversed_dir, bool):
        return _failure(PocketFeatureError("INVALID_ARGUMENT", "reversed_dir must be a boolean"))
    return _PocketFeatureRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=sketch_name,
        pocket_name=PocketName(pocket_name),
        length=float(length),
        body_name=body_name,
        symmetric=symmetric,
        reversed_dir=reversed_dir,
    )


@dataclass(slots=True)
class _PocketFeatureExecution:
    collaborators: PocketFeatureCollaborators
    request: _PocketFeatureRequest
    created: PocketFeatureReceipt | None = None
    inspected: PocketFeatureInspection | None = None

    def apply(self, doc: PocketFeatureDocument) -> None:
        self.created = apply_pocket_feature(
            doc,
            self.request.sketch_name,
            self.request.pocket_name,
            self.request.length,
            self.request.body_name,
            self.request.symmetric,
            self.request.reversed_dir,
            self.collaborators,
        )

    def inspect(self, doc: PocketFeatureReadDocument) -> None:
        if self.created is None:
            raise PocketFeatureError(
                "INVALID_POCKET_FEATURE_RESULT",
                "Pocket creation did not return an identity receipt",
            )
        self.inspected = read_pocket_feature_result(doc, self.created)

    def run(self) -> PocketFeatureResult:
        result = run_pocket_feature_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_pocket_feature_uncertain(
                "POCKET_FEATURE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected Pocket result",
                committed=True,
            )
        return make_pocket_feature_success(self.inspected.name, self.inspected.label)


def run_pocket_feature(
    collaborators: PocketFeatureCollaborators,
    doc_name: object,
    sketch_name: object,
    pocket_name: object,
    length: object,
    body_name: object = None,
    symmetric: object = False,
    reversed_dir: object = False,
) -> PocketFeatureResult:
    request = build_pocket_feature_request(
        doc_name, sketch_name, pocket_name, length, body_name, symmetric, reversed_dir
    )
    if isinstance(request, dict):
        return request
    return _PocketFeatureExecution(collaborators, request).run()


class _PocketFeatureRpcFacade(Protocol):
    _cad_collaborators: PocketFeatureCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_pocket_feature(
    self: _PocketFeatureRpcFacade,
    doc_name: str,
    sketch_name: str,
    pocket_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_pocket_feature(
            collaborators,
            doc_name,
            sketch_name,
            pocket_name,
            length,
            body_name,
            symmetric,
            reversed_dir,
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("pocket_feature", rpc_pocket_feature)


__all__ = [
    "PocketFeatureCollaborators",
    "PocketFeatureError",
    "PocketFeatureInspection",
    "PocketFeatureReceipt",
    "apply_pocket_feature",
    "build_pocket_feature_request",
    "read_pocket_feature_result",
    "rpc_pocket_feature",
    "run_pocket_feature",
    "TYPED_RPC_HANDLER",
]
