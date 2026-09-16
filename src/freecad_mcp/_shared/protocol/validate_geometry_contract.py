"""Versioned, stdlib-only wire contract for ``validate_geometry``."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, NewType, NotRequired, Protocol, TypedDict, runtime_checkable

VALIDATE_GEOMETRY_CONTRACT_VERSION: Literal[1] = 1

DocumentName = NewType("DocumentName", str)
ObjectName = NewType("ObjectName", str)


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


class ValidateGeometryCollaborators(Protocol):
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
class ValidateGeometryRequest:
    """Validated internal request."""

    doc_name: DocumentName
    obj_name: ObjectName


class ValidateGeometrySuccess(TypedDict):
    """Only response shape that may become outward MCP success."""

    contract_version: Literal[1]
    success: Literal[True]
    ok: Literal[True]
    outcome: Literal["observed"]
    retry_safe: Literal[False]
    object: str
    is_null: bool
    is_valid: bool
    is_closed: bool
    volume_mm3: float
    area_mm2: float
    face_count: int
    edge_count: int
    vertex_count: int
    shape_type: str
    check_ok: bool
    check_errors: object


class ValidateGeometryFailure(TypedDict):
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


class ValidateGeometryUncertain(TypedDict):
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


ValidateGeometryResult = ValidateGeometrySuccess | ValidateGeometryFailure | ValidateGeometryUncertain

_CORE_KEYS = frozenset(
    {
        "area_mm2",
        "check_errors",
        "check_ok",
        "committed",
        "contract_version",
        "diagnostics",
        "edge_count",
        "error",
        "error_code",
        "face_count",
        "is_closed",
        "is_null",
        "is_valid",
        "native_message",
        "native_status",
        "object",
        "ok",
        "outcome",
        "retry_safe",
        "rollback_failed",
        "rollback_succeeded",
        "shape_type",
        "success",
        "vertex_count",
        "volume_mm3",
    }
)


def make_validate_geometry_success(
    object: str, is_null: bool, is_valid: bool, is_closed: bool, volume_mm3: float, area_mm2: float, face_count: int, edge_count: int, vertex_count: int, shape_type: str, check_ok: bool, check_errors: object,
) -> ValidateGeometrySuccess:
    """Construct a complete observed result."""

    return {
        "contract_version": VALIDATE_GEOMETRY_CONTRACT_VERSION,
        "success": True,
        "ok": True,
        "outcome": "observed",
        "retry_safe": False,
        "object": object,
        "is_null": is_null,
        "is_valid": is_valid,
        "is_closed": is_closed,
        "volume_mm3": volume_mm3,
        "area_mm2": area_mm2,
        "face_count": face_count,
        "edge_count": edge_count,
        "vertex_count": vertex_count,
        "shape_type": shape_type,
        "check_ok": check_ok,
        "check_errors": check_errors,
    }


def make_validate_geometry_failure(
    error_code: str,
    error: str,
    *,
    retry_safe: bool = True,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> ValidateGeometryFailure:
    """Construct a proven non-committed result."""

    result: ValidateGeometryFailure = {
        "contract_version": VALIDATE_GEOMETRY_CONTRACT_VERSION,
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


def make_validate_geometry_uncertain(
    error_code: str,
    error: str,
    *,
    committed: bool | None,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> ValidateGeometryUncertain:
    """Construct a result that explicitly forbids automatic replay."""

    result: ValidateGeometryUncertain = {
        "contract_version": VALIDATE_GEOMETRY_CONTRACT_VERSION,
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


def _invalid_response(response: dict[str, object]) -> ValidateGeometryUncertain:
    committed = response.get("committed") is True or response.get("native_status") == "Committed"
    rollback_failed = (
        response.get("rollback_failed") is True
        or response.get("rollback_succeeded") is False
        or response.get("native_status") == "RollbackFailed"
    )
    code = (
        "VALIDATE_GEOMETRY_COMMITTED_RESPONSE_INVALID"
        if committed
        else "VALIDATE_GEOMETRY_ROLLBACK_UNCERTAIN"
        if rollback_failed
        else "INVALID_VALIDATE_GEOMETRY_RESPONSE"
    )
    return make_validate_geometry_uncertain(
        code,
        "validate_geometry returned an invalid contract response; document state requires reconciliation",
        committed=True if committed else None,
        diagnostics={"response": response},
    )


def parse_validate_geometry_response(raw_response: object) -> ValidateGeometryResult:
    """Validate all three wire variants; unknown state always stays uncertain."""
    response = _response_object(raw_response)
    if response is None:
        return make_validate_geometry_uncertain(
            "INVALID_RPC_RESPONSE",
            "validate_geometry returned a non-object response",
            committed=None,
        )
    version = response.get("contract_version")
    details = _response_details(response)
    if type(version) is not int or version != VALIDATE_GEOMETRY_CONTRACT_VERSION or details is None:
        return _invalid_response(response)

    object_name = response.get("object")
    is_null = response.get("is_null")
    is_valid = response.get("is_valid")
    is_closed = response.get("is_closed")
    volume_mm3 = response.get("volume_mm3")
    area_mm2 = response.get("area_mm2")
    face_count = response.get("face_count")
    edge_count = response.get("edge_count")
    vertex_count = response.get("vertex_count")
    shape_type = response.get("shape_type")
    check_ok = response.get("check_ok")
    check_errors = response.get("check_errors")
    if _valid_success(response) and isinstance(object_name, str) and isinstance(is_null, bool) and isinstance(is_valid, bool) and isinstance(is_closed, bool) and isinstance(volume_mm3, (int, float)) and not isinstance(volume_mm3, bool) and isinstance(area_mm2, (int, float)) and not isinstance(area_mm2, bool) and type(face_count) is int and type(edge_count) is int and type(vertex_count) is int and isinstance(shape_type, str) and isinstance(check_ok, bool) and check_errors is not None:
        return make_validate_geometry_success(object_name, is_null, is_valid, is_closed, float(volume_mm3), float(area_mm2), face_count, edge_count, vertex_count, shape_type, check_ok, check_errors)

    error_code = response.get("error_code")
    error = response.get("error")
    success_keys = {'object', 'is_null', 'is_valid', 'is_closed', 'volume_mm3', 'area_mm2', 'face_count', 'edge_count', 'vertex_count', 'shape_type', 'check_ok', 'check_errors'}
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
            return make_validate_geometry_failure(
                error_code,
                error,
                retry_safe=response["retry_safe"] is True,
                **details,
            )
        if _valid_uncertain(response):
            committed = response["committed"]
            assert committed is None or isinstance(committed, bool)
            return make_validate_geometry_uncertain(error_code, error, committed=committed, **details)
    return _invalid_response(response)


__all__ = [
    "VALIDATE_GEOMETRY_CONTRACT_VERSION",
    "ValidateGeometryCollaborators",
    "ValidateGeometryFailure",
    "ValidateGeometryRequest",
    "ValidateGeometryResult",
    "ValidateGeometrySuccess",
    "ValidateGeometryUncertain",
    "MutationDocument",
    "MutationObject",
    "MutationReadDocument",
    "DocumentName",
    "make_validate_geometry_failure",
    "make_validate_geometry_success",
    "make_validate_geometry_uncertain",
    "parse_validate_geometry_response",
]
