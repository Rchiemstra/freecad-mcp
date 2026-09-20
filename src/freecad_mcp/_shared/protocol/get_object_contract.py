"""Versioned, stdlib-only wire contract for ``get_object``."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, NewType, NotRequired, Protocol, TypedDict, runtime_checkable

GET_OBJECT_CONTRACT_VERSION: Literal[1] = 1

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


class GetObjectCollaborators(Protocol):
    """Complete typed boundary between the handler and native bridge."""

    freecad: object

    def serialize_object(self, obj: object) -> dict[str, object]:
        """Serialize a document object for wire transport."""

        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class GetObjectRequest:
    """Validated internal request."""

    doc_name: DocumentName
    obj_name: ObjectName


class GetObjectSuccess(TypedDict):
    """Only response shape that may become outward MCP success."""

    contract_version: Literal[1]
    success: Literal[True]
    ok: Literal[True]
    outcome: Literal["observed"]
    retry_safe: Literal[False]
    object: str
    object_data: dict[str, object]


class GetObjectFailure(TypedDict):
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


class GetObjectUncertain(TypedDict):
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


GetObjectResult = GetObjectSuccess | GetObjectFailure | GetObjectUncertain

_PROVEN_REJECTION_CODES = frozenset(
    {
        "DOCUMENT_NOT_FOUND",
        "GET_OBJECT_SERIALIZE_FAILED",
        "OBJECT_NOT_FOUND",
    }
)

_CORE_KEYS = frozenset(
    {
        "committed",
        "contract_version",
        "diagnostics",
        "error",
        "error_code",
        "frame",
        "native_message",
        "native_status",
        "object",
        "ok",
        "outcome",
        "retry_safe",
        "rollback_failed",
        "rollback_succeeded",
        "success",
        "unit",
        "volume_mm3",
        "used_linked_object",
    }
)


def make_get_object_success(
    object: str, object_data: dict[str, object],
) -> GetObjectSuccess:
    """Construct a complete observed result."""

    return {
        "contract_version": GET_OBJECT_CONTRACT_VERSION,
        "success": True,
        "ok": True,
        "outcome": "observed",
        "retry_safe": False,
        "object": object,
        "object_data": object_data,
    }


def make_get_object_failure(
    error_code: str,
    error: str,
    *,
    retry_safe: bool = True,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> GetObjectFailure:
    """Construct a proven non-committed result."""

    result: GetObjectFailure = {
        "contract_version": GET_OBJECT_CONTRACT_VERSION,
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


def make_get_object_uncertain(
    error_code: str,
    error: str,
    *,
    committed: bool | None,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> GetObjectUncertain:
    """Construct a result that explicitly forbids automatic replay."""

    result: GetObjectUncertain = {
        "contract_version": GET_OBJECT_CONTRACT_VERSION,
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


def _invalid_response(response: dict[str, object]) -> GetObjectUncertain:
    committed = response.get("committed") is True or response.get("native_status") == "Committed"
    rollback_failed = (
        response.get("rollback_failed") is True
        or response.get("rollback_succeeded") is False
        or response.get("native_status") == "RollbackFailed"
    )
    code = (
        "GET_OBJECT_COMMITTED_RESPONSE_INVALID"
        if committed
        else "GET_OBJECT_ROLLBACK_UNCERTAIN"
        if rollback_failed
        else "INVALID_GET_OBJECT_RESPONSE"
    )
    return make_get_object_uncertain(
        code,
        "get_object returned an invalid contract response; document state requires reconciliation",
        committed=True if committed else None,
        diagnostics={"response": response},
    )


def reconstruct_get_object_from_remote_error(exc: object) -> GetObjectResult:
    """Rebuild a typed contract result from a JSON-RPC transport error."""

    from .json_rpc_client import JsonRpcRemoteError

    if not isinstance(exc, JsonRpcRemoteError):
        return make_get_object_uncertain(
            "GET_OBJECT_TRANSPORT_UNCERTAIN",
            f"get_object response unavailable: {exc}",
            committed=None,
        )

    data = exc.data if isinstance(exc.data, Mapping) else None
    if data:
        parsed = parse_get_object_response(data)
        if parsed["success"] is True or parsed["outcome"] == "rejected":
            return parsed
        if parsed["error_code"].startswith("GUI_TIMEOUT"):
            return parsed
        if parsed["error_code"] != "INVALID_GET_OBJECT_RESPONSE":
            return parsed

        error_code = data.get("error_code")
        error = data.get("error") or data.get("message")
        if (
            isinstance(error_code, str)
            and error_code.startswith("GUI_TIMEOUT")
            and isinstance(error, str)
        ):
            return make_get_object_uncertain(error_code, error, committed=None)
        if (
            data.get("success") is False
            and isinstance(error_code, str)
            and error_code in _PROVEN_REJECTION_CODES
            and isinstance(error, str)
        ):
            return make_get_object_failure(error_code, error)

    code = str(exc.semantic_code)
    if code.startswith("GUI_TIMEOUT"):
        return make_get_object_uncertain(code, exc.message, committed=None)
    if code in _PROVEN_REJECTION_CODES:
        return make_get_object_failure(code, exc.message)

    return make_get_object_uncertain(
        "GET_OBJECT_TRANSPORT_UNCERTAIN",
        f"get_object response unavailable: {exc}",
        committed=None,
    )


def get_object_wire_from_server(
    server: object,
    doc_name: str,
    obj_name: str,
) -> dict[str, object]:
    """Return a contract dict from ``server.get_object`` without raising lookup errors."""

    from .json_rpc_client import JsonRpcRemoteError

    try:
        raw: object = server.get_object(doc_name, obj_name)
    except JsonRpcRemoteError as exc:
        return dict(reconstruct_get_object_from_remote_error(exc))
    except Exception as exc:
        return dict(
            make_get_object_uncertain(
                "GET_OBJECT_TRANSPORT_UNCERTAIN",
                f"get_object response unavailable: {exc}",
                committed=None,
            )
        )
    return dict(parse_get_object_response(raw))


def parse_get_object_response(raw_response: object) -> GetObjectResult:
    """Validate all three wire variants; unknown state always stays uncertain."""
    if isinstance(raw_response, str):
        lowered = raw_response.lower()
        if "timed out" in lowered or lowered == "timeout":
            return make_get_object_uncertain(
                "GUI_TIMEOUT_DURING_EXECUTION",
                raw_response,
                committed=None,
            )
        return make_get_object_uncertain(
            "INVALID_RPC_RESPONSE",
            "get_object returned a non-object response",
            committed=None,
        )

    response = _response_object(raw_response)
    if response is None:
        return make_get_object_uncertain(
            "INVALID_RPC_RESPONSE",
            "get_object returned a non-object response",
            committed=None,
        )
    error_code = response.get("error_code")
    if (
        response.get("success") is False
        and isinstance(error_code, str)
        and error_code.startswith("GUI_TIMEOUT")
        and isinstance(response.get("error"), str)
    ):
        return make_get_object_uncertain(
            error_code,
            str(response["error"]),
            committed=None,
        )

    version = response.get("contract_version")
    details = _response_details(response)
    if type(version) is not int or version != GET_OBJECT_CONTRACT_VERSION or details is None:
        return _invalid_response(response)

    object_name = response.get("object")
    object_data = response.get("object_data")
    if (
        _valid_success(response)
        and isinstance(object_name, str)
        and isinstance(object_data, dict)
        and all(isinstance(key, str) for key in object_data)
    ):
        return make_get_object_success(object_name, object_data)

    error_code = response.get("error_code")
    error = response.get("error")
    success_keys = {'object', 'object_data'}
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
            return make_get_object_failure(
                error_code,
                error,
                retry_safe=response["retry_safe"] is True,
                **details,
            )
        if _valid_uncertain(response):
            committed = response["committed"]
            assert committed is None or isinstance(committed, bool)
            return make_get_object_uncertain(error_code, error, committed=committed, **details)
    return _invalid_response(response)


__all__ = [
    "GET_OBJECT_CONTRACT_VERSION",
    "DocumentName",
    "GetObjectCollaborators",
    "GetObjectFailure",
    "GetObjectRequest",
    "GetObjectResult",
    "GetObjectSuccess",
    "GetObjectUncertain",
    "MutationDocument",
    "MutationObject",
    "MutationReadDocument",
    "get_object_wire_from_server",
    "make_get_object_failure",
    "make_get_object_success",
    "make_get_object_uncertain",
    "parse_get_object_response",
    "reconstruct_get_object_from_remote_error",
]
