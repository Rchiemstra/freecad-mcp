"""Versioned, stdlib-only wire contract for ``sketch_constrain_tangent``."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, NewType, NotRequired, Protocol, TypedDict, runtime_checkable

SKETCH_CONSTRAIN_TANGENT_CONTRACT_VERSION: Literal[1] = 1

DocumentName = NewType("DocumentName", str)
SketchName = NewType("SketchName", str)


class SketchVector(Protocol):
    x: float
    y: float
    z: float

    @property
    def Length(self) -> float: ...

    def __sub__(self, other: SketchVector) -> SketchVector: ...


class SketchGeom(Protocol):
    Construction: bool


class SketchGeometryList(Protocol):
    def __getitem__(self, index: int) -> SketchGeom: ...


class SketchCurve(Protocol):
    def setPoles(self, poles: list[SketchVector]) -> object: ...

    def interpolate(self, points: list[SketchVector], periodic: bool = False) -> object: ...

    def buildFromPoles(
        self, poles: list[SketchVector], periodic: bool, degree: int
    ) -> object: ...

    def buildFromPolesMultsKnots(
        self,
        poles: list[SketchVector],
        multiplicities: list[int],
        knots: list[float],
        periodic: bool,
        degree: int,
        weights: list[float],
    ) -> object: ...


class SketchPart(Protocol):
    def LineSegment(self, start: SketchVector, end: SketchVector) -> object: ...

    def Circle(self, center: SketchVector, normal: SketchVector, radius: float) -> object: ...

    def ArcOfCircle(self, circle: object, start: float, end: float) -> object: ...

    def Ellipse(
        self, major_pt: SketchVector, minor_radius: float, center: SketchVector
    ) -> object: ...

    def ArcOfEllipse(self, ellipse: object, start: float, end: float) -> object: ...

    def Point(self, vector: SketchVector) -> object: ...

    def BSplineCurve(self) -> SketchCurve: ...

    def BezierCurve(self) -> SketchCurve: ...


class SketchFreeCAD(Protocol):
    def Vector(self, x: float, y: float, z: float) -> SketchVector: ...


class SketchSketcher(Protocol):
    def Constraint(self, *args: object) -> object: ...


class SketchObject(Protocol):
    @property
    def Name(self) -> str: ...

    @property
    def TypeId(self) -> str: ...

    @property
    def GeometryCount(self) -> int: ...

    @property
    def ConstraintCount(self) -> int: ...

    @property
    def Geometry(self) -> SketchGeometryList: ...

    def isDerivedFrom(self, type_name: str) -> bool: ...

    def addGeometry(self, geometry: object, construction: bool = False) -> int: ...

    def addConstraint(self, constraint: object) -> int: ...

    def renameConstraint(self, index: int, name: str) -> object: ...

    def trim(self, geo_index: int, point: SketchVector) -> object: ...

    def extend(self, geo_index: int, increment: float, end_point: int) -> object: ...

    def split(self, geo_index: int, point: SketchVector) -> object: ...

    def fillet(
        self,
        geo1: int,
        geo2: int,
        point1: SketchVector,
        point2: SketchVector,
        radius: float,
        trim: bool,
        create_point: bool,
    ) -> object: ...

    def addSymmetric(self, indices: Sequence[int], symmetry_geo: int) -> object: ...

    def toggleConstruction(self, geo_index: int) -> object: ...


class SketchReadDocument(Protocol):
    @property
    def Name(self) -> str: ...

    def getObject(self, name: str) -> SketchObject | None: ...


class SketchDocument(SketchReadDocument, Protocol):
    def addObject(self, object_type: str, name: str) -> object: ...


@runtime_checkable
class NativeSketchDocument(SketchDocument, Protocol):
    def commitCompatibilityMutation(
        self,
        callback: Callable[[], object],
        *,
        structural: bool = False,
        postcondition: Callable[[], object] | None = None,
    ) -> object: ...


class SketchConstrainTangentCollaborators(Protocol):
    @property
    def freecad(self) -> SketchFreeCAD: ...

    @property
    def part(self) -> SketchPart: ...

    @property
    def sketcher(self) -> SketchSketcher: ...

    def validate_document_invariants(self, document: SketchReadDocument) -> object: ...

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        postcondition: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class SketchConstrainTangentRequest:
    doc_name: DocumentName
    sketch_name: SketchName
    geo1: int
    geo2: int


class SketchConstrainTangentSuccess(TypedDict):
    contract_version: Literal[1]
    success: Literal[True]
    ok: Literal[True]
    outcome: Literal["committed"]
    committed: Literal[True]
    retry_safe: Literal[False]
    sketch: SketchName
    constraint_index: int


class SketchConstrainTangentFailure(TypedDict):
    contract_version: Literal[1]
    success: Literal[False]
    ok: Literal[False]
    outcome: Literal["rejected"]
    committed: Literal[False]
    retry_safe: bool
    error_code: str
    error: str
    native_status: NotRequired[str | None]
    native_message: NotRequired[str]
    rollback_succeeded: NotRequired[bool]
    rollback_failed: NotRequired[bool]
    diagnostics: NotRequired[dict[str, object]]


class SketchConstrainTangentUncertain(TypedDict):
    contract_version: Literal[1]
    success: Literal[False]
    ok: Literal[False]
    outcome: Literal["uncertain"]
    committed: bool | None
    retry_safe: Literal[False]
    error_code: str
    error: str
    native_status: NotRequired[str | None]
    native_message: NotRequired[str]
    rollback_succeeded: NotRequired[bool]
    rollback_failed: NotRequired[bool]
    diagnostics: NotRequired[dict[str, object]]


SketchConstrainTangentResult = SketchConstrainTangentSuccess | SketchConstrainTangentFailure | SketchConstrainTangentUncertain

_CORE_KEYS = frozenset(
    {
        "contract_version",
        "success",
        "ok",
        "outcome",
        "committed",
        "retry_safe",
        "sketch",
        "error_code",
        "error",
        "native_status",
        "native_message",
        "rollback_succeeded",
        "rollback_failed",
        "diagnostics",
        "constraint_index",
    }
)


def make_sketch_constrain_tangent_success(sketch: SketchName, constraint_index: int) -> SketchConstrainTangentSuccess:
    return {
        "contract_version": SKETCH_CONSTRAIN_TANGENT_CONTRACT_VERSION,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "sketch": sketch,
        "constraint_index": constraint_index,
    }


def make_sketch_constrain_tangent_failure(
    error_code: str,
    error: str,
    *,
    retry_safe: bool = True,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> SketchConstrainTangentFailure:
    result: SketchConstrainTangentFailure = {
        "contract_version": SKETCH_CONSTRAIN_TANGENT_CONTRACT_VERSION,
        "success": False,
        "ok": False,
        "outcome": "rejected",
        "committed": False,
        "retry_safe": retry_safe,
        "error_code": error_code,
        "error": error,
    }
    if native_status is not None:
        result["native_status"] = native_status
    if native_message is not None:
        result["native_message"] = native_message
    if rollback_succeeded is not None:
        result["rollback_succeeded"] = rollback_succeeded
    if rollback_failed is not None:
        result["rollback_failed"] = rollback_failed
    if diagnostics:
        result["diagnostics"] = diagnostics
    return result


def make_sketch_constrain_tangent_uncertain(
    error_code: str,
    error: str,
    *,
    committed: bool | None,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> SketchConstrainTangentUncertain:
    result: SketchConstrainTangentUncertain = {
        "contract_version": SKETCH_CONSTRAIN_TANGENT_CONTRACT_VERSION,
        "success": False,
        "ok": False,
        "outcome": "uncertain",
        "committed": committed,
        "retry_safe": False,
        "error_code": error_code,
        "error": error,
    }
    if native_status is not None:
        result["native_status"] = native_status
    if native_message is not None:
        result["native_message"] = native_message
    if rollback_succeeded is not None:
        result["rollback_succeeded"] = rollback_succeeded
    if rollback_failed is not None:
        result["rollback_failed"] = rollback_failed
    if diagnostics:
        result["diagnostics"] = diagnostics
    return result


def _response_object(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, Mapping):
        return None
    result: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            return None
        result[key] = value
    return result


class _ResponseDetails(TypedDict, total=False):
    native_status: str | None
    native_message: str
    rollback_succeeded: bool
    rollback_failed: bool
    diagnostics: dict[str, object]


def _read_rollback_flags(response: dict[str, object], details: _ResponseDetails) -> bool:
    for key in ("rollback_succeeded", "rollback_failed"):
        if key in response:
            flag = response[key]
            if not isinstance(flag, bool):
                return False
            if key == "rollback_succeeded":
                details["rollback_succeeded"] = flag
            else:
                details["rollback_failed"] = flag
    return True


def _response_details(response: dict[str, object]) -> _ResponseDetails | None:
    details: _ResponseDetails = {}
    if "native_status" in response:
        status = response["native_status"]
        if status is not None and not isinstance(status, str):
            return None
        details["native_status"] = status
    if "native_message" in response:
        message = response["native_message"]
        if not isinstance(message, str):
            return None
        details["native_message"] = message
    if not _read_rollback_flags(response, details):
        return None
    diagnostics = _response_object(response.get("diagnostics", {}))
    if diagnostics is None:
        return None
    diagnostics.update({key: value for key, value in response.items() if key not in _CORE_KEYS})
    if diagnostics:
        details["diagnostics"] = diagnostics
    return details


def _valid_success(response: dict[str, object]) -> bool:
    return (
        response.get("success") is True
        and response.get("ok") is True
        and response.get("outcome") == "committed"
        and response.get("committed") is True
        and response.get("retry_safe") is False
        and "error" not in response
        and "error_code" not in response
        and response.get("native_status", "Committed") == "Committed"
        and "rollback_succeeded" not in response
        and response.get("rollback_failed", False) is False
        and response.get("completion_uncertain", False) is False
    )


def _valid_rejection(response: dict[str, object]) -> bool:
    return (
        response.get("outcome") == "rejected"
        and response.get("committed") is False
        and isinstance(response.get("retry_safe"), bool)
        and response.get("rollback_succeeded", True) is True
        and response.get("rollback_failed", False) is False
        and response.get("native_status") not in {"Committed", "RollbackFailed"}
        and response.get("completion_uncertain", False) is False
    )


def _valid_uncertain(response: dict[str, object]) -> bool:
    return (
        response.get("outcome") == "uncertain"
        and "committed" in response
        and (response["committed"] is None or isinstance(response["committed"], bool))
        and response.get("retry_safe") is False
        and not (response["committed"] is False and response.get("native_status") == "Committed")
        and not (
            response.get("rollback_succeeded") is True
            and response.get("rollback_failed") is True
        )
    )


def _invalid_response(response: dict[str, object]) -> SketchConstrainTangentUncertain:
    committed = response.get("committed") is True or response.get("native_status") == "Committed"
    rollback_failed = (
        response.get("rollback_failed") is True
        or response.get("rollback_succeeded") is False
        or response.get("native_status") == "RollbackFailed"
    )
    code = (
        "SKETCH_CONSTRAIN_TANGENT_COMMITTED_RESPONSE_INVALID"
        if committed
        else "SKETCH_CONSTRAIN_TANGENT_ROLLBACK_UNCERTAIN"
        if rollback_failed
        else "INVALID_SKETCH_CONSTRAIN_TANGENT_RESPONSE"
    )
    return make_sketch_constrain_tangent_uncertain(
        code,
        "sketch_constrain_tangent returned an invalid contract response; document state requires reconciliation",
        committed=True if committed else None,
        diagnostics={"response": response},
    )


def parse_sketch_constrain_tangent_response(raw_response: object) -> SketchConstrainTangentResult:
    response = _response_object(raw_response)
    if response is None:
        return make_sketch_constrain_tangent_uncertain(
            "INVALID_RPC_RESPONSE",
            "sketch_constrain_tangent returned a non-object response",
            committed=None,
        )
    version = response.get("contract_version")
    details = _response_details(response)
    if type(version) is not int or version != SKETCH_CONSTRAIN_TANGENT_CONTRACT_VERSION or details is None:
        return _invalid_response(response)

    sketch = response.get("sketch")
    constraint_index = response.get("constraint_index")
    if (
        _valid_success(response)
        and isinstance(sketch, str)
        and sketch.strip()
        and type(constraint_index) is int
    ):
        return make_sketch_constrain_tangent_success(SketchName(sketch), constraint_index)

    error_code = response.get("error_code")
    error = response.get("error")
    if (
        response.get("success") is False
        and response.get("ok") is False
        and isinstance(error_code, str)
        and error_code.strip()
        and isinstance(error, str)
        and error.strip()
        and "sketch" not in response
        and "constraint_index" not in response
    ):
        if _valid_rejection(response):
            return make_sketch_constrain_tangent_failure(
                error_code,
                error,
                retry_safe=response["retry_safe"] is True,
                **details,
            )
        if _valid_uncertain(response):
            committed = response["committed"]
            assert committed is None or isinstance(committed, bool)
            return make_sketch_constrain_tangent_uncertain(error_code, error, committed=committed, **details)
    return _invalid_response(response)


__all__ = [
    "SKETCH_CONSTRAIN_TANGENT_CONTRACT_VERSION",
    "SketchConstrainTangentCollaborators",
    "SketchConstrainTangentFailure",
    "SketchConstrainTangentRequest",
    "SketchConstrainTangentResult",
    "SketchConstrainTangentSuccess",
    "SketchConstrainTangentUncertain",
    "DocumentName",
    "NativeSketchDocument",
    "SketchDocument",
    "SketchFreeCAD",
    "SketchName",
    "SketchObject",
    "SketchPart",
    "SketchReadDocument",
    "SketchSketcher",
    "make_sketch_constrain_tangent_failure",
    "make_sketch_constrain_tangent_success",
    "make_sketch_constrain_tangent_uncertain",
    "parse_sketch_constrain_tangent_response",
]
