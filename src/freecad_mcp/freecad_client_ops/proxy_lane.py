"""Thread-safe JSON-RPC HTTP proxy lane."""

from __future__ import annotations

import itertools
import json
import threading
from collections.abc import Callable, Mapping
from typing import Any

from .._shared.protocol.json_rpc_client import (
    JSON_RPC_HTTP_PATH,
    JSON_RPC_PROTOCOL_HEADER,
    JSON_RPC_PROTOCOL_VALUE,
    JsonRpcProtocolMismatchError,
    JsonRpcRemoteError,
    decode_json_rpc_response,
    encode_json_rpc_request,
)
from .json_rpc_http_transport import JsonRpcHttpTransport, _JsonRpcHttpResponseError

_SECRET_HEADERS = frozenset(
    {
        "x-mcp-session-token",
        "x-mcp-lease-token",
        "x-mcp-lease-credentials",
    }
)


def _request_header_secrets(headers: list[tuple[str, str]]) -> tuple[str, ...]:
    secrets = []
    for name, value in headers:
        normalized_name = str(name).lower()
        text = str(value)
        if normalized_name not in _SECRET_HEADERS or not text:
            continue
        secrets.append(text)
        if normalized_name != "x-mcp-lease-credentials":
            continue
        try:
            credentials = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(credentials, list):
            for credential in credentials:
                if not isinstance(credential, Mapping):
                    continue
                token = credential.get("token")
                if isinstance(token, str) and token:
                    secrets.append(token)
    return tuple(sorted(set(secrets), key=len, reverse=True))


def _redact_remote_error(
    error: JsonRpcRemoteError,
    secrets: tuple[str, ...],
) -> JsonRpcRemoteError:
    def scrub(value: Any) -> Any:
        if isinstance(value, str):
            safe = value
            for secret in secrets:
                safe = safe.replace(secret, "[REDACTED]")
            return safe
        if isinstance(value, Mapping):
            return {scrub(str(key)): scrub(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return tuple(scrub(item) for item in value)
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    safe_message = scrub(error.message)
    safe_data = scrub(error.data)
    if safe_message == error.message and safe_data == error.data:
        return error
    return JsonRpcRemoteError(
        error.code,
        safe_message,
        data=safe_data,
        request_id=error.request_id,
    )


class ProxyLane:
    """Thread-safe JSON-RPC lane with independent connection state.

    General work and control work use different instances so a long modelling
    call cannot hold the transport lock needed by cancellation or status queries.
    """

    def __init__(
        self,
        uri: str,
        timeout: float,
        header_provider: Callable[[str, tuple[Any, ...]], tuple[tuple[str, str], ...]],
    ) -> None:
        self._header_provider = header_provider
        self._lock = threading.RLock()
        self._request_ids = itertools.count(1)
        self.transport = JsonRpcHttpTransport(uri, timeout=timeout)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        from .proxy_method import ProxyMethod

        return ProxyMethod(self, name)

    def call(
        self,
        method: str,
        *args: Any,
        extra_headers: tuple[tuple[str, str], ...] = (),
        notification: bool = False,
    ) -> Any:
        with self._lock:
            request_id = None if notification else next(self._request_ids)
            payload = encode_json_rpc_request(
                method,
                tuple(args),
                request_id=request_id,
                notification=notification,
            )
            request_headers = [
                *self._header_provider(method, tuple(args)),
                *extra_headers,
                (JSON_RPC_PROTOCOL_HEADER, JSON_RPC_PROTOCOL_VALUE),
            ]
            request_secrets = _request_header_secrets(request_headers)
            self.transport.extra_headers = list(request_headers)
            try:
                try:
                    status, response_headers, response = self.transport.request(
                        JSON_RPC_HTTP_PATH,
                        payload,
                        request_headers,
                    )
                except _JsonRpcHttpResponseError as exc:
                    raise JsonRpcProtocolMismatchError(
                        "FreeCAD RPC endpoint returned an invalid bounded HTTP response"
                    ) from exc
                protocol_values = response_headers.get(
                    JSON_RPC_PROTOCOL_HEADER.lower(), ()
                )
                if protocol_values != (JSON_RPC_PROTOCOL_VALUE,):
                    raise JsonRpcProtocolMismatchError(
                        "FreeCAD RPC protocol header mismatch: expected JSON-RPC 2.0",
                        actual=protocol_values,
                    )
                if notification:
                    if status != 204 or response:
                        raise JsonRpcProtocolMismatchError(
                            "FreeCAD RPC notification received an unexpected response",
                            actual=status,
                        )
                    return None
                if status != 200:
                    raise JsonRpcProtocolMismatchError(
                        "FreeCAD RPC endpoint rejected the JSON-RPC request",
                        actual=status,
                    )
                try:
                    return decode_json_rpc_response(response, expected_id=request_id)
                except JsonRpcRemoteError as exc:
                    safe_error = _redact_remote_error(exc, request_secrets)
                raise safe_error
            finally:
                self.transport.extra_headers = []

    def notify(
        self,
        method: str,
        *args: Any,
        extra_headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        """Send a fire-and-forget JSON-RPC notification on this lane."""

        self.call(
            method,
            *args,
            extra_headers=extra_headers,
            notification=True,
        )

    def close(self) -> None:
        # Transport close is independently synchronized and aborts active I/O.
        # Do not wait for the per-lane call lock before delivering cancellation.
        self.transport.extra_headers = []
        self.transport.close()
