"""Versioned, stdlib-only wire contract for ``get_sketch_geometry``."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, NewType, NotRequired, Protocol, TypedDict, runtime_checkable

GET_SKETCH_GEOMETRY_CONTRACT_VERSION: Literal[1] = 1

DocumentName = NewType("DocumentName", str)
SketchName = NewType("SketchName", str)


class MutationObject(Protocol):
    """Object surface inspected before native commit."""

    @property
    def Name(self) -> str: ...

    @property
    def Label(self) -> str: ...

    @property
    def TypeId(self) -> str: ...

    def isDerivedFrom(self, type_name: str) -> bool: ...


class MutationReadDocument(Protocol):
    """Read-only document surface available after native recompute."""

    @property
    def Name(self) -> str: ...

    def getObject(self, name: str) -> MutationObject | None: ...


class MutationDocument(MutationReadDocument, Protocol):
    """Narrow mutation surface available only to the apply callback."""

    def addObject(self, object_type: str, name: str) -> MutationObject: ...

    def removeObject(self, name: str) -> None: ...


@runtime_checkable
class NativeMutationDocument(MutationDocument, Protocol):
    """Runtime-checkable native surface required before apply starts."""

    def commitCompatibilityMutation(
        self,
        callback: Callable[[], object],
        *,
        structural: bool = False,
        postcondition: Callable[[], object] | None = None,
    ) -> object: ...


class GetSketchGeometryCollaborators(Protocol):
    """Complete typed boundary between the handler and native bridge."""

    def validate_document_invariants(self, document: MutationReadDocument) -> object:
        """Validate the recomputed document before commit."""

        ...

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        postcondition: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        """Run the mutation through its fixed native transaction policy."""

        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class GetSketchGeometryRequest:
    """Validated internal request."""

    doc_name: DocumentName
    sketch_name: SketchName
    include_constraints: bool
    include_external: bool
    global_coords: bool


class GetSketchGeometrySuccess(TypedDict):
    contract_version: Literal[1]
    success: Literal[True]
    ok: Literal[True]
    outcome: Literal["observed"]
    retry_safe: Literal[False]
    sketch_name: str
    geometry_count: int
    geometry: object
    constraints: object
    external_geometry: object


class GetSketchGeometryFailure(TypedDict):
    """A proven rejection or successful rollback."""

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


class GetSketchGeometryUncertain(TypedDict):
    """A non-success result whose model state makes automatic retry unsafe."""

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


GetSketchGeometryResult = GetSketchGeometrySuccess | GetSketchGeometryFailure | GetSketchGeometryUncertain

_CORE_KEYS = frozenset(
    {
        "committed",
        "constraints",
        "contract_version",
        "diagnostics",
        "error",
        "error_code",
        "external_geometry",
        "geometry",
        "geometry_count",
        "native_message",
        "native_status",
        "ok",
        "outcome",
        "retry_safe",
        "rollback_failed",
        "rollback_succeeded",
        "sketch_name",
        "success",
    }
)


def make_get_sketch_geometry_success(
    sketch_name: str, geometry_count: int, geometry: object, constraints: object | None = None, external_geometry: object | None = None,
) -> GetSketchGeometrySuccess:
    return {
        "contract_version": GET_SKETCH_GEOMETRY_CONTRACT_VERSION,
        "success": True,
        "ok": True,
        "outcome": "observed",
        "retry_safe": False,
        "sketch_name": sketch_name,
        "geometry_count": geometry_count,
        "geometry": geometry,
        "constraints": constraints,
        "external_geometry": external_geometry,
    }


def make_get_sketch_geometry_failure(
    error_code: str,
    error: str,
    *,
    retry_safe: bool = True,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> GetSketchGeometryFailure:
    """Construct a proven non-committed result."""

    result: GetSketchGeometryFailure = {
        "contract_version": GET_SKETCH_GEOMETRY_CONTRACT_VERSION,
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


def make_get_sketch_geometry_uncertain(
    error_code: str,
    error: str,
    *,
    committed: bool | None,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> GetSketchGeometryUncertain:
    """Construct a result that explicitly forbids automatic replay."""

    result: GetSketchGeometryUncertain = {
        "contract_version": GET_SKETCH_GEOMETRY_CONTRACT_VERSION,
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
        and response.get("outcome") == "observed"
        and response.get("retry_safe") is False
        and "error" not in response
        and "error_code" not in response
        and "committed" not in response
        and "native_status" not in response
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


def _invalid_response(response: dict[str, object]) -> GetSketchGeometryUncertain:
    committed = response.get("committed") is True or response.get("native_status") == "Committed"
    rollback_failed = (
        response.get("rollback_failed") is True
        or response.get("rollback_succeeded") is False
        or response.get("native_status") == "RollbackFailed"
    )
    code = (
        "GET_SKETCH_GEOMETRY_COMMITTED_RESPONSE_INVALID"
        if committed
        else "GET_SKETCH_GEOMETRY_ROLLBACK_UNCERTAIN"
        if rollback_failed
        else "INVALID_GET_SKETCH_GEOMETRY_RESPONSE"
    )
    return make_get_sketch_geometry_uncertain(
        code,
        "get_sketch_geometry returned an invalid contract response; document state requires reconciliation",
        committed=True if committed else None,
        diagnostics={"response": response},
    )


def parse_get_sketch_geometry_response(raw_response: object) -> GetSketchGeometryResult:
    """Validate all three wire variants; unknown state always stays uncertain."""
    response = _response_object(raw_response)
    if response is None:
        return make_get_sketch_geometry_uncertain(
            "INVALID_RPC_RESPONSE",
            "get_sketch_geometry returned a non-object response",
            committed=None,
        )
    version = response.get("contract_version")
    details = _response_details(response)
    if type(version) is not int or version != GET_SKETCH_GEOMETRY_CONTRACT_VERSION or details is None:
        return _invalid_response(response)

    sketch_name = response.get("sketch_name")
    geometry_count = response.get("geometry_count")
    geometry = response.get("geometry")
    if _valid_success(response) and isinstance(sketch_name, str) and type(geometry_count) is int and geometry is not None:
        return make_get_sketch_geometry_success(sketch_name, geometry_count, geometry, response.get("constraints"), response.get("external_geometry"))

    error_code = response.get("error_code")
    error = response.get("error")
    success_keys = {'sketch_name', 'geometry_count', 'geometry', 'constraints', 'external_geometry'}
    if (
        response.get("success") is False
        and response.get("ok") is False
        and isinstance(error_code, str)
        and error_code.strip()
        and isinstance(error, str)
        and error.strip()
        and success_keys.isdisjoint(response)
    ):
        if _valid_rejection(response):
            return make_get_sketch_geometry_failure(
                error_code,
                error,
                retry_safe=response["retry_safe"] is True,
                **details,
            )
        if _valid_uncertain(response):
            committed = response["committed"]
            assert committed is None or isinstance(committed, bool)
            return make_get_sketch_geometry_uncertain(error_code, error, committed=committed, **details)
    return _invalid_response(response)


__all__ = [
    "GET_SKETCH_GEOMETRY_CONTRACT_VERSION",
    "GetSketchGeometryCollaborators",
    "GetSketchGeometryFailure",
    "GetSketchGeometryRequest",
    "GetSketchGeometryResult",
    "GetSketchGeometrySuccess",
    "GetSketchGeometryUncertain",
    "MutationDocument",
    "MutationObject",
    "MutationReadDocument",
    "DocumentName",
    "make_get_sketch_geometry_failure",
    "make_get_sketch_geometry_success",
    "make_get_sketch_geometry_uncertain",
    "parse_get_sketch_geometry_response",
]
