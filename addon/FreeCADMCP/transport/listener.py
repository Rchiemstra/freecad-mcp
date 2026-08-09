"""Bounded-capacity HTTP listener for the add-on JSON-RPC transport."""

from __future__ import annotations

import contextlib
import inspect as _inspect
import ipaddress
import logging
import re
import socket
import threading
import time
from collections.abc import Callable
from collections.abc import Mapping as _Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from xmlrpc.server import SimpleXMLRPCServer

try:
    from .._shared.protocol.json_rpc import (
        JSON_RPC_INVALID_PARAMS as _JSON_RPC_INVALID_PARAMS,
    )
    from .._shared.protocol.json_rpc import (
        JSON_RPC_METHOD_NOT_FOUND as _JSON_RPC_METHOD_NOT_FOUND,
    )
    from .._shared.protocol.json_rpc import MAX_JSON_RPC_BYTES as _MAX_JSON_RPC_BYTES
    from .._shared.protocol.json_rpc_client import (
        JSON_RPC_HTTP_PATH as _JSON_RPC_HTTP_PATH,
    )
    from .._shared.protocol.json_rpc_client import (
        JSON_RPC_PROTOCOL_HEADER as _JSON_RPC_PROTOCOL_HEADER,
    )
    from .._shared.protocol.json_rpc_client import (
        JSON_RPC_PROTOCOL_VALUE as _JSON_RPC_PROTOCOL_VALUE,
    )
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from _shared.protocol.json_rpc import (
        JSON_RPC_INVALID_PARAMS as _JSON_RPC_INVALID_PARAMS,
    )
    from _shared.protocol.json_rpc import (
        JSON_RPC_METHOD_NOT_FOUND as _JSON_RPC_METHOD_NOT_FOUND,
    )
    from _shared.protocol.json_rpc import MAX_JSON_RPC_BYTES as _MAX_JSON_RPC_BYTES
    from _shared.protocol.json_rpc_client import (
        JSON_RPC_HTTP_PATH as _JSON_RPC_HTTP_PATH,
    )
    from _shared.protocol.json_rpc_client import (
        JSON_RPC_PROTOCOL_HEADER as _JSON_RPC_PROTOCOL_HEADER,
    )
    from _shared.protocol.json_rpc_client import (
        JSON_RPC_PROTOCOL_VALUE as _JSON_RPC_PROTOCOL_VALUE,
    )

from .ip_filter import _parse_allowed_ips
from .json_rpc_errors import json_rpc_error_from_result
from .json_rpc_transport import JsonRpcError, JsonRpcTransport
from .request_handler import JsonRpcRequestHandler

__all__ = ["JsonRpcListener", "xmlrpc_safe_response"]

logger = logging.getLogger("FreeCADMCP.rpc_server")

_XMLRPC_INT_MIN = -(2**31)
_XMLRPC_INT_MAX = (2**31) - 1
_JSON_RPC_SERVER_BUSY = -32000
_JSON_RPC_SERVER_STOPPING = -32004
_XMLRPC_DEPRECATION_BODY = (
    b'{"error":"xmlrpc_retired","message":"XML-RPC is retired; '
    b'use JSON-RPC 2.0 at /jsonrpc"}'
)
_PROTOCOL_MISMATCH_BODY = (
    b'{"jsonrpc":"2.0","id":null,"error":{"code":-32005,'
    b'"message":"Protocol mismatch","data":{"expected":"jsonrpc-2.0"}}}'
)


def xmlrpc_safe_response(value: Any) -> Any:
    """Return a response value encodable by the retired XML-RPC marshaller."""

    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if _XMLRPC_INT_MIN <= value <= _XMLRPC_INT_MAX:
            return value
        return str(value)
    if isinstance(value, dict):
        return {key: xmlrpc_safe_response(item) for key, item in value.items()}
    if isinstance(value, list):
        return [xmlrpc_safe_response(item) for item in value]
    if isinstance(value, tuple):
        return tuple(xmlrpc_safe_response(item) for item in value)
    return value


class JsonRpcListener(SimpleXMLRPCServer):
    """Serve bounded JSON-RPC requests through one injected transport factory."""

    CONTROL_METHODS = frozenset(
        {
            "ping",
            "handshake_v2",
            "invoke_v2_control",
            "lease_heartbeat_batch",
            "lease_reconcile",
            "get_request_status",
            "cancel_request",
            "get_worker_status",
            "cancel_worker_job",
            "shutdown_rpc_server",
        }
    )

    def __init__(
        self,
        addr: Any,
        allowed_ips_str: str = "127.0.0.1",
        *,
        requestHandler: type[JsonRpcRequestHandler] = JsonRpcRequestHandler,
        transport_factory: Callable[..., Any] = JsonRpcTransport,
        result_to_error: Callable[[Any], _Mapping[str, Any] | None] | None = (
            json_rpc_error_from_result
        ),
        capture_request_identity: Callable[..., None] | None = None,
        clear_request_identity: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        if not callable(requestHandler):
            raise TypeError("requestHandler must be callable")
        if not callable(transport_factory):
            raise TypeError("transport_factory must be callable")
        if result_to_error is not None and not callable(result_to_error):
            raise TypeError("result_to_error must be callable or None")
        if capture_request_identity is not None and not callable(
            capture_request_identity
        ):
            raise TypeError("capture_request_identity must be callable or None")
        if clear_request_identity is not None and not callable(clear_request_identity):
            raise TypeError("clear_request_identity must be callable or None")

        self._allowed_networks = _parse_allowed_ips(allowed_ips_str)
        self._handler_slots = threading.BoundedSemaphore(5)
        self._general_slots = threading.BoundedSemaphore(3)
        self._control_slots = threading.BoundedSemaphore(2)
        self._accepting_requests = True
        self._accepting_lock = threading.Lock()
        self._request_deadlines: dict[int, dict[str, Any]] = {}
        self._request_deadlines_lock = threading.Lock()
        self.capture_request_identity = capture_request_identity
        self.clear_request_identity = clear_request_identity
        self.json_rpc_max_body_bytes = _MAX_JSON_RPC_BYTES
        self.json_rpc_read_timeout_seconds = 5.0
        self.json_rpc_http_path = _JSON_RPC_HTTP_PATH
        self.json_rpc_protocol_header = _JSON_RPC_PROTOCOL_HEADER
        self.json_rpc_protocol_value = _JSON_RPC_PROTOCOL_VALUE
        super().__init__(addr, requestHandler=requestHandler, **kwargs)
        self._handler_executor = ThreadPoolExecutor(
            max_workers=5, thread_name_prefix="FreeCADMCP-RPC"
        )
        try:
            self._json_rpc_transport = transport_factory(
                self._dispatch_json_rpc,
                result_to_error=result_to_error,
            )
        except BaseException:
            self._handler_executor.shutdown(wait=True, cancel_futures=True)
            super().server_close()
            raise

    def _registered_method(self, method: str) -> Callable[..., Any]:
        if method.startswith("_"):
            raise JsonRpcError(_JSON_RPC_METHOD_NOT_FOUND, "Method not found")
        function = self.funcs.get(method)
        if function is None:
            function = getattr(getattr(self, "instance", None), method, None)
        if not callable(function):
            raise JsonRpcError(_JSON_RPC_METHOD_NOT_FOUND, "Method not found")
        return function

    def _validated_json_rpc_params(self, method: str, params: Any) -> tuple[Any, ...]:
        function = self._registered_method(method)
        try:
            signature = _inspect.signature(function)
            if isinstance(params, _Mapping):
                bound = signature.bind(**params)
                bound.apply_defaults()
                if bound.kwargs:
                    raise TypeError("keyword-only parameters are unsupported")
                return bound.args
            signature.bind(*params)
        except (TypeError, ValueError) as exc:
            raise JsonRpcError(
                _JSON_RPC_INVALID_PARAMS,
                "Invalid params",
            ) from exc
        return tuple(params)

    def _dispatch_json_rpc(self, method: str, params: Any) -> Any:
        method_params = self._validated_json_rpc_params(method, params)
        control = method in self.CONTROL_METHODS
        slots = self._control_slots if control else self._general_slots
        with self._accepting_lock:
            accepting = self._accepting_requests
        if not accepting:
            raise JsonRpcError(_JSON_RPC_SERVER_STOPPING, "Server stopping")
        if not slots.acquire(blocking=False):
            lane = "control" if control else "general"
            raise JsonRpcError(
                _JSON_RPC_SERVER_BUSY,
                "Server busy",
                {"reason": "server_busy", "lane": lane},
            )
        try:
            return self._dispatch(method, method_params)
        finally:
            slots.release()

    def _read_json_rpc_post(self, handler: Any) -> bytes | None:
        """Validate and read one bounded JSON-RPC request body."""

        handler.close_connection = True
        deadline_expired, deadline_at = self._take_request_deadline(
            handler.connection
        )
        if deadline_expired:
            return None
        length = self._json_rpc_content_length(handler)
        if length is None:
            return None
        return self._read_json_rpc_body(handler, length, deadline_at)

    def _handle_json_rpc_post(self, handler: Any, payload: bytes) -> None:
        """Dispatch a validated JSON-RPC body on the listener."""

        response = self._json_rpc_transport.handle_bytes(payload)
        if response is None:
            handler.send_response(204)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(response)))
        handler.end_headers()
        handler.wfile.write(response)

    def _json_rpc_content_length(self, handler: Any) -> int | None:
        content_lengths = handler.headers.get_all("Content-Length", [])
        transfer_encodings = handler.headers.get_all("Transfer-Encoding", [])
        if transfer_encodings or len(content_lengths) > 1:
            handler.send_error(400)
            return None
        if not content_lengths:
            handler.send_error(411)
            return None
        content_length = content_lengths[0].strip(" \t")
        if not re.fullmatch(r"[0-9]+", content_length):
            handler.send_error(400)
            return None
        try:
            length = int(content_length)
        except ValueError:
            handler.send_error(400)
            return None
        if length > self.json_rpc_max_body_bytes:
            handler.send_error(413)
            return None
        return length

    def _read_json_rpc_body(
        self, handler: Any, length: int, deadline_at: float
    ) -> bytes | None:
        chunks: list[bytes] = []
        remaining = length
        while remaining:
            timeout = deadline_at - time.monotonic()
            if timeout <= 0:
                handler.send_error(408)
                return None
            try:
                handler.connection.settimeout(timeout)
                chunk = handler.rfile.read1(min(remaining, 65536))
            except OSError:
                handler.send_error(408)
                return None
            if not chunk:
                handler.send_error(400)
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        if time.monotonic() > deadline_at:
            handler.send_error(408)
            return None
        handler.connection.settimeout(self.json_rpc_read_timeout_seconds)
        return b"".join(chunks)

    def _handle_xmlrpc_retired_post(self, handler: Any) -> None:
        """Return the bounded XML-RPC retirement response without reading a body."""

        self._cancel_request_deadline(handler.connection)
        handler.close_connection = True
        handler.send_response(410, "Gone")
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(_XMLRPC_DEPRECATION_BODY)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Deprecation", "true")
        handler.send_header("Link", '</jsonrpc>; rel="successor-version"')
        handler.end_headers()
        handler.wfile.write(_XMLRPC_DEPRECATION_BODY)

    def _handle_json_rpc_protocol_mismatch(self, handler: Any) -> None:
        """Reject an explicitly incompatible protocol before reading its body."""

        self._cancel_request_deadline(handler.connection)
        handler.close_connection = True
        handler.send_response(409, "Conflict")
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(_PROTOCOL_MISMATCH_BODY)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(_PROTOCOL_MISMATCH_BODY)

    def process_request(self, request: Any, client_address: Any) -> None:
        with self._accepting_lock:
            admitted = self._accepting_requests and self._handler_slots.acquire(False)
        if not admitted:
            self.shutdown_request(request)
            return
        try:
            request.settimeout(self.json_rpc_read_timeout_seconds)
            self._handler_executor.submit(
                self._process_request_in_pool,
                request,
                client_address,
            )
        except Exception:
            self._handler_slots.release()
            self.shutdown_request(request)
            raise

    def _process_request_in_pool(self, request: Any, client_address: Any) -> None:
        deadline: dict[str, Any] = {
            "at": time.monotonic() + self.json_rpc_read_timeout_seconds,
            "expired": threading.Event(),
        }

        def expire_request() -> None:
            with self._request_deadlines_lock:
                if self._request_deadlines.get(id(request)) is not deadline:
                    return
                deadline["expired"].set()
            with contextlib.suppress(OSError):
                request.shutdown(socket.SHUT_RD)

        timer = threading.Timer(self.json_rpc_read_timeout_seconds, expire_request)
        timer.daemon = True
        deadline["timer"] = timer
        with self._request_deadlines_lock:
            self._request_deadlines[id(request)] = deadline
        timer.start()
        try:
            self.finish_request(request, client_address)
        except Exception:  # server boundary reports via handle_error
            self.handle_error(request, client_address)
        finally:
            self._cancel_request_deadline(request)
            self.shutdown_request(request)
            self._handler_slots.release()

    def _take_request_deadline(self, request: Any) -> tuple[bool, float]:
        with self._request_deadlines_lock:
            deadline = self._request_deadlines.pop(id(request), None)
        if deadline is None:
            return False, time.monotonic() + self.json_rpc_read_timeout_seconds
        deadline["timer"].cancel()
        return deadline["expired"].is_set(), deadline["at"]

    def _cancel_request_deadline(self, request: Any) -> None:
        self._take_request_deadline(request)

    def _marshaled_dispatch(
        self,
        data: bytes,
        dispatch_method: Callable[..., Any] | None = None,
        path: str | None = None,
    ) -> bytes:
        """Keep direct compatibility calls non-dispatching after retirement."""

        del data, dispatch_method, path
        return _XMLRPC_DEPRECATION_BODY

    def begin_shutdown(self) -> None:
        with self._accepting_lock:
            self._accepting_requests = False
        transport = getattr(self, "_json_rpc_transport", None)
        if transport is not None:
            transport.begin_shutdown()

    def server_close(self) -> None:
        failures: list[BaseException] = []
        try:
            self.begin_shutdown()
        except BaseException as exc:
            failures.append(exc)
        try:
            super().server_close()
        except BaseException as exc:
            failures.append(exc)
        executor = getattr(self, "_handler_executor", None)
        if executor is not None:
            try:
                executor.shutdown(wait=True, cancel_futures=False)
            except BaseException as exc:
                failures.append(exc)
        if len(failures) == 1:
            raise failures[0]
        if failures:
            raise BaseExceptionGroup("transport listener cleanup failed", failures)

    def verify_request(self, request: Any, client_address: Any) -> bool:
        del request
        client_ip = client_address[0]
        try:
            address = ipaddress.ip_address(client_ip)
            for network in self._allowed_networks:
                if address in network:
                    return True
        except ValueError:
            pass
        logger.warning("MCP RPC: rejected connection from %s", client_ip)
        return False
