"""Client-side JSON-RPC 2.0 framing and protocol negotiation."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from .json_rpc import (
    JSON_RPC_VERSION,
    MAX_JSON_RPC_BYTES,
    JsonRpcFramingError,
    _parse_json,
    _payload_text,
)

JSON_RPC_HTTP_PATH = "/jsonrpc"
JSON_RPC_PROTOCOL_HEADER = "X-FreeCAD-MCP-Protocol"
JSON_RPC_PROTOCOL_VALUE = "jsonrpc-2.0"

_MISSING = object()

__all__ = (
    "JSON_RPC_HTTP_PATH",
    "JSON_RPC_PROTOCOL_HEADER",
    "JSON_RPC_PROTOCOL_VALUE",
    "JsonRpcProtocolMismatchError",
    "JsonRpcRemoteError",
    "decode_json_rpc_response",
    "encode_json_rpc_request",
    "unwrap_nested_remote_error",
)

_USELESS_REMOTE_MESSAGES = frozenset(
    {"", "RPC failed", "Authenticated RPC failed"}
)


class JsonRpcProtocolMismatchError(RuntimeError):
    """The peer did not speak the required JSON-RPC transport version."""

    def __init__(self, message: str, *, actual: object = None) -> None:
        self.expected = JSON_RPC_PROTOCOL_VALUE
        self.actual = actual
        super().__init__(message)


class JsonRpcRemoteError(RuntimeError):
    """A structured JSON-RPC error returned by the FreeCAD add-on."""

    def __init__(
        self,
        code: int,
        message: str,
        *,
        data: Any = _MISSING,
        request_id: str | int | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.request_id = request_id
        self.data = None if data is _MISSING else copy.deepcopy(data)
        semantic = self.data.get("error_code") if isinstance(self.data, Mapping) else None
        self.semantic_code = str(semantic or code)
        super().__init__(f"FreeCAD RPC error {code}: {message}")


def _nested_failure_payload(container: Mapping[str, Any]) -> Mapping[str, Any] | None:
    inner = container.get("result")
    if isinstance(inner, Mapping) and (
        inner.get("success") is False or inner.get("ok") is False
    ):
        return inner
    if container.get("success") is False or container.get("ok") is False:
        return container
    return None


def _nested_failure_message(payload: Mapping[str, Any]) -> str | None:
    for key in ("error", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, Mapping):
            nested = value.get("message")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def unwrap_nested_remote_error(error: JsonRpcRemoteError) -> JsonRpcRemoteError:
    """Surface invoke_v2 inner failures when the transport returned a useless message."""

    message = str(error.message or "").strip()
    if message and message not in _USELESS_REMOTE_MESSAGES:
        return error
    data = error.data
    if not isinstance(data, Mapping):
        return error
    nested = _nested_failure_payload(data)
    if nested is None:
        return error
    nested_message = _nested_failure_message(nested)
    if not nested_message:
        return error
    new_data = copy.deepcopy(data)
    nested_code = nested.get("error_code") or nested.get("code")
    if nested_code and "error_code" not in new_data:
        new_data["error_code"] = str(nested_code)
    return JsonRpcRemoteError(
        error.code,
        nested_message,
        data=new_data,
        request_id=error.request_id,
    )


def _valid_id(value: object) -> bool:
    return value is None or type(value) in {str, int}


def encode_json_rpc_request(
    method: str,
    params: list[Any] | tuple[Any, ...] | dict[str, Any],
    *,
    request_id: str | int | None = None,
    notification: bool = False,
) -> bytes:
    """Encode one bounded request or notification."""

    if not isinstance(method, str):
        raise TypeError("JSON-RPC method must be a string")
    if not isinstance(params, (list, tuple, dict)):
        raise TypeError("JSON-RPC params must be an array or object")
    if not notification and not _valid_id(request_id):
        raise TypeError("JSON-RPC request ID must be a string, integer, or null")
    document: dict[str, Any] = {
        "jsonrpc": JSON_RPC_VERSION,
        "method": method,
        "params": params,
    }
    if not notification:
        document["id"] = request_id
    try:
        payload = json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (RecursionError, TypeError, UnicodeEncodeError, ValueError) as exc:
        raise ValueError("JSON-RPC request is not encodable") from exc
    if len(payload) > MAX_JSON_RPC_BYTES:
        raise ValueError("JSON-RPC request exceeds the transport limit")
    return payload


def decode_json_rpc_response(
    payload: bytes | str,
    *,
    expected_id: str | int | None,
) -> Any:
    """Validate one response, returning its result or raising its native error."""

    if not _valid_id(expected_id):
        raise TypeError("expected JSON-RPC ID must be a string, integer, or null")
    try:
        document = _parse_json(_payload_text(payload))
    except JsonRpcFramingError as exc:
        raise JsonRpcProtocolMismatchError(
            "FreeCAD RPC endpoint did not return a valid JSON-RPC 2.0 response"
        ) from exc
    if not isinstance(document, dict):
        raise JsonRpcProtocolMismatchError(
            "FreeCAD RPC endpoint returned a non-object JSON-RPC response"
        )
    actual_version = document.get("jsonrpc")
    if actual_version != JSON_RPC_VERSION:
        raise JsonRpcProtocolMismatchError(
            "FreeCAD RPC protocol version mismatch: expected JSON-RPC 2.0",
            actual=actual_version,
        )
    actual_id = document.get("id", _MISSING)
    if actual_id is _MISSING or not _valid_id(actual_id) or actual_id != expected_id:
        raise JsonRpcProtocolMismatchError(
            "FreeCAD RPC response ID did not match its request"
        )
    has_result = "result" in document
    has_error = "error" in document
    if has_result == has_error:
        raise JsonRpcProtocolMismatchError(
            "FreeCAD RPC response must contain exactly one result or error"
        )
    if has_result:
        return document["result"]
    error = document["error"]
    if not isinstance(error, Mapping):
        raise JsonRpcProtocolMismatchError(
            "FreeCAD RPC response contained an invalid error object"
        )
    code = error.get("code")
    message = error.get("message")
    if type(code) is not int or not isinstance(message, str):
        raise JsonRpcProtocolMismatchError(
            "FreeCAD RPC response contained an invalid error code or message"
        )
    raise unwrap_nested_remote_error(
        JsonRpcRemoteError(
            code,
            message,
            data=error.get("data", _MISSING),
            request_id=actual_id,
        )
    )
