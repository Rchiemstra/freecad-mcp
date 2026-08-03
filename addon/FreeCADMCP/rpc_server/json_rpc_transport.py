"""Callback-injected JSON-RPC 2.0 framing and dispatch transport."""

from __future__ import annotations

import logging as _logging
import threading as _threading
from collections.abc import Callable as _Callable
from collections.abc import Mapping as _Mapping
from typing import Any as _Any

try:
    from .._shared.protocol.json_rpc import (
        JSON_RPC_INTERNAL_ERROR as _JSON_RPC_INTERNAL_ERROR,
    )
    from .._shared.protocol.json_rpc import (
        JSON_RPC_INVALID_REQUEST as _JSON_RPC_INVALID_REQUEST,
    )
    from .._shared.protocol.json_rpc import (
        JsonRpcFramingError as _JsonRpcFramingError,
    )
    from .._shared.protocol.json_rpc import (
        JsonRpcInvalidRequest as _JsonRpcInvalidRequest,
    )
    from .._shared.protocol.json_rpc import (
        decode_json_rpc_payload as _decode_json_rpc_payload,
    )
    from .._shared.protocol.json_rpc import (
        encode_json_rpc_responses as _encode_json_rpc_responses,
    )
    from .._shared.protocol.json_rpc import (
        json_rpc_error as _json_rpc_error,
    )
    from .._shared.protocol.json_rpc import (
        json_rpc_success as _json_rpc_success,
    )
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from _shared.protocol.json_rpc import (
        JSON_RPC_INTERNAL_ERROR as _JSON_RPC_INTERNAL_ERROR,
    )
    from _shared.protocol.json_rpc import (
        JSON_RPC_INVALID_REQUEST as _JSON_RPC_INVALID_REQUEST,
    )
    from _shared.protocol.json_rpc import (
        JsonRpcFramingError as _JsonRpcFramingError,
    )
    from _shared.protocol.json_rpc import (
        JsonRpcInvalidRequest as _JsonRpcInvalidRequest,
    )
    from _shared.protocol.json_rpc import (
        decode_json_rpc_payload as _decode_json_rpc_payload,
    )
    from _shared.protocol.json_rpc import (
        encode_json_rpc_responses as _encode_json_rpc_responses,
    )
    from _shared.protocol.json_rpc import (
        json_rpc_error as _json_rpc_error,
    )
    from _shared.protocol.json_rpc import (
        json_rpc_success as _json_rpc_success,
    )

_logger = _logging.getLogger("FreeCADMCP.rpc_server")

_SERVER_STOPPING = -32004
_MISSING = object()

__all__ = ("JsonRpcError", "JsonRpcTransport")


class JsonRpcError(Exception):
    """A structured JSON-RPC error safe to return across the wire."""

    def __init__(self, code: int, message: str, data: _Any = _MISSING) -> None:
        if isinstance(code, bool) or not isinstance(code, int):
            raise TypeError("JSON-RPC error code must be an integer")
        if not isinstance(message, str):
            raise TypeError("JSON-RPC error message must be a string")
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def as_dict(self) -> dict[str, _Any]:
        """Return the JSON-RPC ``error`` object represented by this exception."""

        value = {"code": self.code, "message": self.message}
        if self.data is not _MISSING:
            value["data"] = self.data
        return value


def _error(code: int, message: str, data: _Any = _MISSING) -> dict[str, _Any]:
    return JsonRpcError(code, message, data).as_dict()


def _response_error(request_id: _Any, error: _Mapping[str, _Any]) -> dict[str, _Any]:
    data = error.get("data", _MISSING)
    if data is _MISSING:
        return _json_rpc_error(request_id, error["code"], error["message"])
    return _json_rpc_error(request_id, error["code"], error["message"], data)


def _ensure_encodable_error(
    response: dict[str, _Any], request_id: _Any
) -> dict[str, _Any]:
    try:
        _encode_json_rpc_responses([response], batch=False)
    except (TypeError, ValueError):
        return _json_rpc_error(request_id, _JSON_RPC_INTERNAL_ERROR, "Internal error")
    return response


def _validated_error(value: _Any) -> dict[str, _Any] | None:
    if value is None:
        return None
    if not isinstance(value, _Mapping):
        raise TypeError("result-to-error callback must return a mapping or None")
    code = value.get("code")
    message = value.get("message")
    data = value.get("data", _MISSING)
    return _error(code, message, data)


class JsonRpcTransport:
    """Decode JSON-RPC requests and route them through one injected dispatch seam.

    ``dispatch`` receives ``(method, params)``. Array parameters are normalized to
    tuples to match the existing XML-RPC dispatch seam; object parameters remain a
    mapping for a named-parameter-aware integration adapter. ``result_to_error`` may
    convert a legacy failure result into a JSON-RPC ``error`` object.
    """

    def __init__(
        self,
        dispatch: _Callable[[str, _Any], _Any],
        *,
        result_to_error: _Callable[[_Any], _Mapping[str, _Any] | None] | None = None,
        exception_to_error: _Callable[[BaseException], JsonRpcError | None]
        | None = None,
    ) -> None:
        if not callable(dispatch):
            raise TypeError("dispatch must be callable")
        self._dispatch = dispatch
        self._result_to_error = result_to_error
        self._exception_to_error = exception_to_error
        self._accepting = True
        self._accepting_lock = _threading.Lock()

    def begin_shutdown(self) -> None:
        """Reject subsequent requests while allowing in-flight dispatch to finish."""

        with self._accepting_lock:
            self._accepting = False

    def handle_bytes(self, payload: bytes) -> bytes | None:
        """Return a UTF-8 JSON response, or ``None`` for notification-only input."""

        try:
            document = _decode_json_rpc_payload(payload)
        except _JsonRpcFramingError as exc:
            response = _json_rpc_error(None, exc.code, exc.message)
            return _encode_json_rpc_responses([response], batch=False)

        responses = [self._handle_item(request) for request in document.requests]
        encoded = _encode_json_rpc_responses(
            [response for response in responses if response is not None],
            batch=document.batch,
        )
        return encoded or None

    def _handle_item(self, request: _Any) -> dict[str, _Any] | None:
        if isinstance(request, _JsonRpcInvalidRequest):
            return _json_rpc_error(
                request.request_id, _JSON_RPC_INVALID_REQUEST, "Invalid Request"
            )

        notification = request.notification
        with self._accepting_lock:
            accepting = self._accepting
        if not accepting:
            if notification:
                return None
            return _response_error(
                request.request_id, _error(_SERVER_STOPPING, "Server stopping")
            )

        dispatch_params = (
            tuple(request.params)
            if isinstance(request.params, list)
            else request.params
        )
        try:
            result = self._dispatch(request.method, dispatch_params)
            mapped = (
                _validated_error(self._result_to_error(result))
                if self._result_to_error is not None
                else None
            )
            if notification:
                return None
            if mapped is not None:
                return _ensure_encodable_error(
                    _response_error(request.request_id, mapped), request.request_id
                )
            response = _json_rpc_success(request.request_id, result)
            _encode_json_rpc_responses([response], batch=False)
            return response
        except JsonRpcError as exc:
            if notification:
                return None
            return _ensure_encodable_error(
                _response_error(request.request_id, exc.as_dict()), request.request_id
            )
        except Exception as exc:  # transport boundary must not leak implementation data
            mapped_exception = self._map_exception(exc)
            if notification:
                _logger.warning(
                    "JSON-RPC notification failed (%s)", type(exc).__name__
                )
                return None
            return _ensure_encodable_error(
                _response_error(request.request_id, mapped_exception.as_dict()),
                request.request_id,
            )

    def _map_exception(self, exc: BaseException) -> JsonRpcError:
        if self._exception_to_error is not None:
            try:
                mapped = self._exception_to_error(exc)
                if mapped is not None:
                    if not isinstance(mapped, JsonRpcError):
                        raise TypeError(
                            "exception-to-error callback must return JsonRpcError or None"
                        )
                    return mapped
            except Exception as mapper_exc:
                _logger.error(
                    "JSON-RPC exception mapper failed (%s)",
                    type(mapper_exc).__name__,
                )
        _logger.error("JSON-RPC dispatch failed (%s)", type(exc).__name__)
        return JsonRpcError(_JSON_RPC_INTERNAL_ERROR, "Internal error")
