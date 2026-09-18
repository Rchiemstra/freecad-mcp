"""Versioned, stdlib-only wire contract for ``get_objects``."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, NewType, NotRequired, Protocol, TypedDict

GET_OBJECTS_CONTRACT_VERSION: Literal[1] = 1

DEFAULT_FIELDS: tuple[str, ...] = ("Name", "Label", "TypeId")
ALLOWED_FIELDS: frozenset[str] = frozenset({"Name", "Label", "TypeId", "Placement"})
DEFAULT_PAGE_SIZE: int = 50
MIN_PAGE_SIZE: int = 1
MAX_PAGE_SIZE: int = 250
MAX_PAGE_PAYLOAD_BYTES: int = 65536

DocumentName = NewType("DocumentName", str)


class GetObjectsCollaborators(Protocol):
    """Complete typed boundary between the handler and native bridge."""

    freecad: object

    def serialize_object(self, obj: object) -> dict[str, object]:
        """Serialize a document object for wire transport."""

        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class GetObjectsRequest:
    """Validated internal request."""

    doc_name: DocumentName
    fields: tuple[str, ...]
    include_properties: tuple[str, ...] | None
    include_shape: bool
    include_view: bool
    page_size: int
    cursor: str | None


class GetObjectsSuccess(TypedDict):
    """Only response shape that may become outward MCP success."""

    contract_version: Literal[1]
    success: Literal[True]
    ok: Literal[True]
    outcome: Literal["observed"]
    retry_safe: Literal[False]
    doc_name: str
    objects: list[dict[str, object]]
    total_count: int
    returned_count: int
    page_size: int
    complete: bool
    next_cursor: str | None
    snapshot_id: str


class GetObjectsFailure(TypedDict):
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


class GetObjectsUncertain(TypedDict):
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


GetObjectsResult = GetObjectsSuccess | GetObjectsFailure | GetObjectsUncertain

_PROVEN_REJECTION_CODES = frozenset(
    {
        "DOCUMENT_NOT_FOUND",
        "INVALID_ARGUMENT",
        "INVALID_CURSOR",
        "PAYLOAD_TOO_LARGE",
    }
)

_STALE_CURSOR_CODE = "STALE_CURSOR"

_CORE_KEYS = frozenset(
    {
        "committed",
        "complete",
        "contract_version",
        "diagnostics",
        "doc_name",
        "error",
        "error_code",
        "native_message",
        "native_status",
        "next_cursor",
        "objects",
        "ok",
        "outcome",
        "page_size",
        "retry_safe",
        "returned_count",
        "rollback_failed",
        "rollback_succeeded",
        "snapshot_id",
        "success",
        "total_count",
    }
)


def compute_snapshot_id(doc_name: str, object_names: list[str]) -> str:
    """Fingerprint document identity plus the current Name set."""

    payload = f"{doc_name}\0" + "\0".join(object_names)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def encode_cursor(snapshot_id: str, offset: int) -> str:
    payload = {
        "v": GET_OBJECTS_CONTRACT_VERSION,
        "snapshot_id": snapshot_id,
        "offset": offset,
    }
    raw = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[str, int] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    snapshot_id = payload.get("snapshot_id")
    offset = payload.get("offset")
    if payload.get("v") != GET_OBJECTS_CONTRACT_VERSION:
        return None
    if not isinstance(snapshot_id, str) or not snapshot_id.strip():
        return None
    if type(offset) is not int or offset < 0:
        return None
    return snapshot_id, offset


def make_get_objects_success(
    *,
    doc_name: str,
    objects: list[dict[str, object]],
    total_count: int,
    returned_count: int,
    page_size: int,
    complete: bool,
    next_cursor: str | None,
    snapshot_id: str,
) -> GetObjectsSuccess:
    return {
        "contract_version": GET_OBJECTS_CONTRACT_VERSION,
        "success": True,
        "ok": True,
        "outcome": "observed",
        "retry_safe": False,
        "doc_name": doc_name,
        "objects": objects,
        "total_count": total_count,
        "returned_count": returned_count,
        "page_size": page_size,
        "complete": complete,
        "next_cursor": next_cursor,
        "snapshot_id": snapshot_id,
    }


def make_get_objects_failure(
    error_code: str,
    error: str,
    *,
    retry_safe: bool = True,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> GetObjectsFailure:
    result: GetObjectsFailure = {
        "contract_version": GET_OBJECTS_CONTRACT_VERSION,
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


def make_get_objects_uncertain(
    error_code: str,
    error: str,
    *,
    committed: bool | None,
    native_status: str | None = None,
    native_message: str | None = None,
    rollback_succeeded: bool | None = None,
    rollback_failed: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> GetObjectsUncertain:
    result: GetObjectsUncertain = {
        "contract_version": GET_OBJECTS_CONTRACT_VERSION,
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


def _read_rollback_flags(
    response: dict[str, object], details: _ResponseDetails
) -> bool:
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
    extras = {key: value for key, value in response.items() if key not in _CORE_KEYS}
    diagnostics.update(extras)
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
        and not (
            response["committed"] is False
            and response.get("native_status") == "Committed"
        )
        and not (
            response.get("rollback_succeeded") is True
            and response.get("rollback_failed") is True
        )
    )


def _invalid_response(response: dict[str, object]) -> GetObjectsUncertain:
    committed = response.get("committed") is True or (
        response.get("native_status") == "Committed"
    )
    rollback_failed = (
        response.get("rollback_failed") is True
        or response.get("rollback_succeeded") is False
        or response.get("native_status") == "RollbackFailed"
    )
    code = (
        "GET_OBJECTS_COMMITTED_RESPONSE_INVALID"
        if committed
        else "GET_OBJECTS_ROLLBACK_UNCERTAIN"
        if rollback_failed
        else "INVALID_GET_OBJECTS_RESPONSE"
    )
    return make_get_objects_uncertain(
        code,
        (
            "get_objects returned an invalid contract response; "
            "document state requires reconciliation"
        ),
        committed=True if committed else None,
        diagnostics={"response": response},
    )


def _proven_rejection_from_remote_data(
    data: Mapping[str, object],
) -> GetObjectsResult | None:
    error_code = data.get("error_code")
    error = data.get("error") or data.get("message")
    if (
        isinstance(error_code, str)
        and error_code.startswith("GUI_TIMEOUT")
        and isinstance(error, str)
    ):
        return make_get_objects_uncertain(error_code, error, committed=None)
    if (
        data.get("success") is False
        and isinstance(error_code, str)
        and error_code in _PROVEN_REJECTION_CODES | {_STALE_CURSOR_CODE}
        and isinstance(error, str)
    ):
        return make_get_objects_failure(
            error_code,
            error,
            retry_safe=error_code == _STALE_CURSOR_CODE,
        )
    return None


def reconstruct_get_objects_from_remote_error(exc: object) -> GetObjectsResult:
    """Rebuild a typed contract result from a JSON-RPC transport error."""

    from .json_rpc_client import JsonRpcRemoteError

    if not isinstance(exc, JsonRpcRemoteError):
        return make_get_objects_uncertain(
            "GET_OBJECTS_TRANSPORT_UNCERTAIN",
            f"get_objects response unavailable: {exc}",
            committed=None,
        )

    data = exc.data if isinstance(exc.data, Mapping) else None
    if data:
        parsed = parse_get_objects_response(data)
        if parsed["success"] is True or parsed["outcome"] == "rejected":
            return parsed
        if parsed["error_code"].startswith("GUI_TIMEOUT"):
            return parsed
        if parsed["error_code"] != "INVALID_GET_OBJECTS_RESPONSE":
            return parsed

        proven = _proven_rejection_from_remote_data(data)
        if proven is not None:
            return proven

    code = str(exc.semantic_code)
    if code.startswith("GUI_TIMEOUT"):
        return make_get_objects_uncertain(code, exc.message, committed=None)
    if code in _PROVEN_REJECTION_CODES:
        return make_get_objects_failure(code, exc.message)
    if code == _STALE_CURSOR_CODE:
        return make_get_objects_failure(code, exc.message, retry_safe=True)

    return make_get_objects_uncertain(
        "GET_OBJECTS_TRANSPORT_UNCERTAIN",
        f"get_objects response unavailable: {exc}",
        committed=None,
    )


def get_objects_wire_from_server(
    server: object,
    doc_name: str,
    fields: object = None,
    include_properties: object = None,
    include_shape: bool = False,
    include_view: bool = False,
    page_size: int = DEFAULT_PAGE_SIZE,
    cursor: object = None,
) -> dict[str, object]:
    """Return a contract dict from ``server.get_objects`` without raising."""

    from .json_rpc_client import JsonRpcRemoteError

    try:
        raw: object = server.get_objects(
            doc_name,
            fields,
            include_properties,
            include_shape,
            include_view,
            page_size,
            cursor,
        )
    except JsonRpcRemoteError as exc:
        return dict(reconstruct_get_objects_from_remote_error(exc))
    except Exception as exc:
        return dict(
            make_get_objects_uncertain(
                "GET_OBJECTS_TRANSPORT_UNCERTAIN",
                f"get_objects response unavailable: {exc}",
                committed=None,
            )
        )
    return dict(parse_get_objects_response(raw))


def _parse_non_mapping_response(raw_response: object) -> GetObjectsResult | None:
    if isinstance(raw_response, str):
        lowered = raw_response.lower()
        if "timed out" in lowered or lowered == "timeout":
            return make_get_objects_uncertain(
                "GUI_TIMEOUT_DURING_EXECUTION",
                raw_response,
                committed=None,
            )
        return make_get_objects_uncertain(
            "INVALID_RPC_RESPONSE",
            "get_objects returned a non-object response",
            committed=None,
        )
    if isinstance(raw_response, list):
        return make_get_objects_uncertain(
            "INVALID_RPC_RESPONSE",
            "get_objects returned a retired bare list response",
            committed=None,
        )
    return None


def _parse_success_response(
    response: dict[str, object],
) -> GetObjectsSuccess | None:
    doc_name = response.get("doc_name")
    objects = response.get("objects")
    total_count = response.get("total_count")
    returned_count = response.get("returned_count")
    page_size = response.get("page_size")
    complete = response.get("complete")
    next_cursor = response.get("next_cursor")
    snapshot_id = response.get("snapshot_id")
    if not (
        _valid_success(response)
        and isinstance(doc_name, str)
        and isinstance(objects, list)
        and all(isinstance(item, dict) for item in objects)
        and type(total_count) is int
        and type(returned_count) is int
        and type(page_size) is int
        and isinstance(complete, bool)
        and (next_cursor is None or isinstance(next_cursor, str))
        and isinstance(snapshot_id, str)
        and snapshot_id.strip()
    ):
        return None
    return make_get_objects_success(
        doc_name=doc_name,
        objects=objects,
        total_count=total_count,
        returned_count=returned_count,
        page_size=page_size,
        complete=complete,
        next_cursor=next_cursor,
        snapshot_id=snapshot_id,
    )


def parse_get_objects_response(raw_response: object) -> GetObjectsResult:
    """Validate all three wire variants; unknown state always stays uncertain."""
    non_mapping = _parse_non_mapping_response(raw_response)
    if non_mapping is not None:
        return non_mapping

    response = _response_object(raw_response)
    if response is None:
        return make_get_objects_uncertain(
            "INVALID_RPC_RESPONSE",
            "get_objects returned a non-object response",
            committed=None,
        )
    error_code = response.get("error_code")
    if (
        response.get("success") is False
        and isinstance(error_code, str)
        and error_code.startswith("GUI_TIMEOUT")
        and isinstance(response.get("error"), str)
    ):
        return make_get_objects_uncertain(
            error_code,
            str(response["error"]),
            committed=None,
        )

    version = response.get("contract_version")
    details = _response_details(response)
    if (
        type(version) is not int
        or version != GET_OBJECTS_CONTRACT_VERSION
        or details is None
    ):
        return _invalid_response(response)

    success = _parse_success_response(response)
    if success is not None:
        return success

    error_code = response.get("error_code")
    error = response.get("error")
    success_keys = {
        "doc_name",
        "objects",
        "total_count",
        "returned_count",
        "page_size",
        "complete",
        "next_cursor",
        "snapshot_id",
    }
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
            return make_get_objects_failure(
                error_code,
                error,
                retry_safe=response["retry_safe"] is True,
                **details,
            )
        if _valid_uncertain(response):
            committed = response["committed"]
            assert committed is None or isinstance(committed, bool)
            return make_get_objects_uncertain(
                error_code, error, committed=committed, **details
            )
    return _invalid_response(response)


__all__ = [
    "ALLOWED_FIELDS",
    "DEFAULT_FIELDS",
    "DEFAULT_PAGE_SIZE",
    "GET_OBJECTS_CONTRACT_VERSION",
    "MAX_PAGE_PAYLOAD_BYTES",
    "MAX_PAGE_SIZE",
    "MIN_PAGE_SIZE",
    "DocumentName",
    "GetObjectsCollaborators",
    "GetObjectsFailure",
    "GetObjectsRequest",
    "GetObjectsResult",
    "GetObjectsSuccess",
    "GetObjectsUncertain",
    "compute_snapshot_id",
    "decode_cursor",
    "encode_cursor",
    "get_objects_wire_from_server",
    "make_get_objects_failure",
    "make_get_objects_success",
    "make_get_objects_uncertain",
    "parse_get_objects_response",
    "reconstruct_get_objects_from_remote_error",
]
