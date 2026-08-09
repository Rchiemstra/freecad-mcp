"""Strict JSON-RPC 2.0 framing shared by the client and add-on."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

JSON_RPC_VERSION = "2.0"
JSON_RPC_PARSE_ERROR = -32700
JSON_RPC_INVALID_REQUEST = -32600
JSON_RPC_METHOD_NOT_FOUND = -32601
JSON_RPC_INVALID_PARAMS = -32602
JSON_RPC_INTERNAL_ERROR = -32603
MAX_JSON_RPC_BYTES = 4 * 1024 * 1024

_MISSING = object()
_MAX_JSON_RPC_BATCH = 1_024
_MAX_JSON_RPC_DEPTH = 128
_MAX_JSON_RPC_ITEMS = 100_000


@dataclass(frozen=True)
class JsonRpcRequest:
    """One validated request or notification from a JSON-RPC payload."""

    method: str
    params: list[Any] | dict[str, Any]
    request_id: str | int | None
    notification: bool


@dataclass(frozen=True)
class JsonRpcInvalidRequest:
    """An invalid batch member that requires an Invalid Request response."""

    request_id: str | int | None = None


@dataclass(frozen=True)
class JsonRpcPayload:
    """A decoded single or batch JSON-RPC payload."""

    requests: tuple[JsonRpcRequest | JsonRpcInvalidRequest, ...]
    batch: bool


class JsonRpcFramingError(ValueError):
    """A payload-level JSON-RPC error that prevents request decoding."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not permitted: {value}")


def _validate_json_structure(value: Any) -> None:
    stack = [(value, 0)]
    visited = 0
    while stack:
        item, depth = stack.pop()
        visited += 1
        if visited > _MAX_JSON_RPC_ITEMS or depth > _MAX_JSON_RPC_DEPTH:
            raise ValueError("JSON-RPC document is too complex")
        if isinstance(item, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in item):
                raise ValueError("JSON-RPC strings must be valid Unicode")
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, dict):
            for key, child in item.items():
                stack.append((key, depth + 1))
                stack.append((child, depth + 1))


def _response_id(value: Any) -> str | int | None:
    if value is None or type(value) in {str, int}:
        return value
    return None


def _decode_request(value: Any) -> JsonRpcRequest | JsonRpcInvalidRequest:
    if not isinstance(value, dict):
        return JsonRpcInvalidRequest()

    request_id = _response_id(value.get("id"))
    has_valid_id = "id" not in value or (
        value.get("id") is None or type(value.get("id")) in {str, int}
    )
    params = value.get("params", [])
    if (
        value.get("jsonrpc") != JSON_RPC_VERSION
        or not isinstance(value.get("method"), str)
        or not isinstance(params, (list, dict))
        or not has_valid_id
    ):
        return JsonRpcInvalidRequest(request_id=request_id)

    return JsonRpcRequest(
        method=value["method"],
        params=params,
        request_id=request_id,
        notification="id" not in value,
    )


def _payload_text(payload: bytes | str) -> str:
    if isinstance(payload, bytes):
        if len(payload) > MAX_JSON_RPC_BYTES:
            raise JsonRpcFramingError(JSON_RPC_PARSE_ERROR, "Parse error")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise JsonRpcFramingError(JSON_RPC_PARSE_ERROR, "Parse error") from exc
    elif isinstance(payload, str):
        text = payload
        try:
            encoded_size = len(text.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise JsonRpcFramingError(JSON_RPC_PARSE_ERROR, "Parse error") from exc
        if encoded_size > MAX_JSON_RPC_BYTES:
            raise JsonRpcFramingError(JSON_RPC_PARSE_ERROR, "Parse error")
    else:
        raise TypeError("JSON-RPC payload must be bytes or text")
    return text


def _parse_json(text: str) -> Any:
    try:
        decoded = json.loads(text, parse_constant=_reject_nonfinite_json)
        _validate_json_structure(decoded)
    except (RecursionError, TypeError, ValueError) as exc:
        raise JsonRpcFramingError(JSON_RPC_PARSE_ERROR, "Parse error") from exc
    return decoded


def decode_json_rpc_payload(payload: bytes | str) -> JsonRpcPayload:
    """Decode and validate one JSON-RPC request or batch."""

    decoded = _parse_json(_payload_text(payload))

    if isinstance(decoded, list):
        if not decoded:
            return JsonRpcPayload((JsonRpcInvalidRequest(),), batch=False)
        if len(decoded) > _MAX_JSON_RPC_BATCH:
            raise JsonRpcFramingError(JSON_RPC_INVALID_REQUEST, "Invalid Request")
        requests = tuple(_decode_request(item) for item in decoded)
        return JsonRpcPayload(requests, batch=True)
    if isinstance(decoded, dict):
        return JsonRpcPayload((_decode_request(decoded),), batch=False)
    return JsonRpcPayload((JsonRpcInvalidRequest(),), batch=False)


def json_rpc_success(request_id: str | int | None, result: Any) -> dict[str, Any]:
    """Build a JSON-RPC success response."""

    return {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "result": result}


def json_rpc_error(
    request_id: str | int | None,
    code: int,
    message: str,
    data: Any = _MISSING,
) -> dict[str, Any]:
    """Build a JSON-RPC error response with optional structured data."""

    error: dict[str, Any] = {"code": int(code), "message": str(message)}
    if data is not _MISSING:
        error["data"] = data
    return {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "error": error}


def encode_json_rpc_responses(
    responses: list[dict[str, Any]], *, batch: bool
) -> bytes:
    """Encode response objects, returning an empty body for notifications."""

    if not responses:
        return b""
    value: Any = responses if batch else responses[0]
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
