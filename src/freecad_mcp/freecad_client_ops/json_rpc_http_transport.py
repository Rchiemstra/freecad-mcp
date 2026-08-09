"""Bounded stdlib HTTP transport for the FreeCAD JSON-RPC endpoint."""

from __future__ import annotations

import http.client
import socket
import threading
import urllib.parse
from collections.abc import Iterable, Mapping
from contextlib import suppress


class _JsonRpcHttpResponseError(ValueError):
    """The peer returned an invalid or oversized HTTP response envelope."""


def _abort_socket(sock: socket.socket | None) -> None:
    if sock is None:
        return
    with suppress(OSError):
        sock.shutdown(socket.SHUT_RDWR)
    with suppress(OSError):
        sock.close()


def _group_headers(
    headers: Iterable[tuple[str, str]],
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for name, value in headers:
        grouped.setdefault(name.lower(), []).append(value)
    return {name: tuple(values) for name, values in grouped.items()}


def _declared_response_length(
    headers: Mapping[str, tuple[str, ...]],
    maximum: int,
) -> int | None:
    content_lengths = headers.get("content-length", ())
    transfer_encodings = headers.get("transfer-encoding", ())
    if len(content_lengths) > 1 or len(transfer_encodings) > 1:
        raise _JsonRpcHttpResponseError(
            "ambiguous JSON-RPC response framing headers"
        )
    if content_lengths and transfer_encodings:
        raise _JsonRpcHttpResponseError(
            "conflicting JSON-RPC response framing headers"
        )
    if not content_lengths:
        return None
    raw_length = content_lengths[0].strip(" \t")
    if not raw_length or any(item not in "0123456789" for item in raw_length):
        raise _JsonRpcHttpResponseError(
            "invalid JSON-RPC response Content-Length"
        )
    try:
        declared = int(raw_length)
    except ValueError as exc:
        raise _JsonRpcHttpResponseError(
            "invalid JSON-RPC response Content-Length"
        ) from exc
    if declared < 0 or declared > maximum:
        raise _JsonRpcHttpResponseError(
            "JSON-RPC response exceeds the configured bound"
        )
    return declared


def _read_bounded_response(
    response: http.client.HTTPResponse,
    *,
    maximum: int,
    declared: int | None,
    deadline_expired: threading.Event,
) -> bytes:
    try:
        body = response.read(maximum + 1)
    except http.client.IncompleteRead as exc:
        raise _JsonRpcHttpResponseError(
            "JSON-RPC response body was shorter than Content-Length"
        ) from exc
    if deadline_expired.is_set():
        raise TimeoutError("FreeCAD JSON-RPC response deadline exceeded")
    if len(body) > maximum:
        raise _JsonRpcHttpResponseError(
            "JSON-RPC response exceeds the configured bound"
        )
    if declared is not None and len(body) != declared:
        raise _JsonRpcHttpResponseError(
            "JSON-RPC response body length did not match Content-Length"
        )
    return body


class JsonRpcHttpTransport:
    """Issue one bounded HTTP POST at a time with a configurable timeout."""

    def __init__(
        self,
        uri: str,
        *,
        timeout: float = 30,
        max_response_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        parsed = urllib.parse.urlsplit(uri)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ValueError("FreeCAD JSON-RPC URI must use http with a host")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("FreeCAD JSON-RPC URI must not include a path or query")
        if timeout <= 0 or max_response_bytes < 1:
            raise ValueError("timeout and response bound must be positive")
        self._host = parsed.hostname
        self._port = parsed.port
        self._timeout = timeout
        self._max_response_bytes = max_response_bytes
        self._state_lock = threading.Lock()
        self._connection: http.client.HTTPConnection | None = None
        self._socket: socket.socket | None = None
        self._closed = False
        # Preserved for callers and tests that inspect request-scoped headers.
        self.extra_headers: list[tuple[str, str]] = []

    def request(
        self,
        path: str,
        payload: bytes,
        headers: Iterable[tuple[str, str]],
    ) -> tuple[int, Mapping[str, tuple[str, ...]], bytes]:
        """POST one request and return status, normalized headers, and body."""

        with self._state_lock:
            if self._closed:
                raise RuntimeError("FreeCAD JSON-RPC transport is closed")
            connection = http.client.HTTPConnection(
                self._host,
                self._port,
                timeout=self._timeout,
            )
            self._connection = connection
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Connection": "close",
        }
        for name, value in headers:
            request_headers[str(name)] = str(value)
        deadline_expired = threading.Event()
        deadline_timer: threading.Timer | None = None
        try:
            connection.connect()
            wire_socket = connection.sock
            with self._state_lock:
                if self._closed:
                    _abort_socket(wire_socket)
                    raise RuntimeError("FreeCAD JSON-RPC transport is closed")
                self._socket = wire_socket

            def expire_deadline() -> None:
                deadline_expired.set()
                _abort_socket(wire_socket)

            deadline_timer = threading.Timer(self._timeout, expire_deadline)
            deadline_timer.daemon = True
            deadline_timer.start()
            connection.request("POST", path, body=payload, headers=request_headers)
            response = connection.getresponse()
            response_headers = _group_headers(response.getheaders())
            declared_length = _declared_response_length(
                response_headers,
                self._max_response_bytes,
            )
            body = _read_bounded_response(
                response,
                maximum=self._max_response_bytes,
                declared=declared_length,
                deadline_expired=deadline_expired,
            )
            return response.status, response_headers, body
        except (OSError, http.client.HTTPException):
            if deadline_expired.is_set():
                raise TimeoutError(
                    "FreeCAD JSON-RPC response deadline exceeded"
                ) from None
            raise
        finally:
            if deadline_timer is not None:
                deadline_timer.cancel()
            connection.close()
            with self._state_lock:
                if self._connection is connection:
                    self._connection = None
                    self._socket = None

    def close(self) -> None:
        """Prevent new calls and close any active HTTP connection."""

        with self._state_lock:
            self._closed = True
            connection = self._connection
            wire_socket = self._socket
        _abort_socket(wire_socket)
        if connection is not None:
            connection.close()
