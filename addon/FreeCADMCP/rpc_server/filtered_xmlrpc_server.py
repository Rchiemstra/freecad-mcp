"""Bounded-capacity IP-filtered XML-RPC and JSON-RPC server."""

import inspect as _inspect
import ipaddress
import logging
import re
import threading
from collections.abc import Mapping as _Mapping
from concurrent.futures import ThreadPoolExecutor
from xmlrpc.client import Fault
from xmlrpc.client import dumps as xmlrpc_dumps
from xmlrpc.client import loads as xmlrpc_loads
from xmlrpc.server import SimpleXMLRPCServer

try:
    from .._shared.protocol.json_rpc import (
        JSON_RPC_INVALID_PARAMS as _JSON_RPC_INVALID_PARAMS,
    )
    from .._shared.protocol.json_rpc import (
        JSON_RPC_METHOD_NOT_FOUND as _JSON_RPC_METHOD_NOT_FOUND,
    )
    from .._shared.protocol.json_rpc import (
        MAX_JSON_RPC_BYTES as _MAX_JSON_RPC_BYTES,
    )
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from _shared.protocol.json_rpc import (
        JSON_RPC_INVALID_PARAMS as _JSON_RPC_INVALID_PARAMS,
    )
    from _shared.protocol.json_rpc import (
        JSON_RPC_METHOD_NOT_FOUND as _JSON_RPC_METHOD_NOT_FOUND,
    )
    from _shared.protocol.json_rpc import (
        MAX_JSON_RPC_BYTES as _MAX_JSON_RPC_BYTES,
    )

from .json_rpc_errors import json_rpc_error_from_result as _json_rpc_error_from_result
from .json_rpc_transport import JsonRpcError as _JsonRpcError
from .json_rpc_transport import JsonRpcTransport as _JsonRpcTransport
from .xmlrpc_identity_handler import McpIdentityRequestHandler

logger = logging.getLogger("FreeCADMCP.rpc_server")

_XMLRPC_INT_MIN = -(2**31)
_XMLRPC_INT_MAX = (2**31) - 1
_JSON_RPC_SERVER_BUSY = -32000
_JSON_RPC_SERVER_STOPPING = -32004

_COMMA_SEP_RE = re.compile(r"^\s*[^,\s]+(\s*,\s*[^,\s]+)*\s*$")


def xmlrpc_safe_response(value):
    """Return a response value encodable by the stdlib XML-RPC marshaller.

    Python's XML-RPC encoder supports only signed 32-bit ``int`` values even
    though lease/save results legitimately contain nanosecond timestamps and
    large file sizes.  Keep protocol booleans and ordinary integers typed, but
    carry out-of-range values as unambiguous decimal strings.  This conversion
    is intentionally outbound-only; addon state and sidecars retain integers.
    """

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


def validate_allowed_ips(allowed_ips_str):
    """Validate a comma-separated string of IP addresses/subnets.

    Returns a ``(valid, errors)`` tuple.  ``valid`` is a list of normalised
    entry strings that passed validation; ``errors`` is a list of
    human-readable error messages (empty when the input is fully valid).

    Checks performed:
    1. The overall string is well-formed comma-separated (no leading/trailing
       commas, no empty entries between commas, not blank).
    2. Each individual entry is a valid IPv4/IPv6 address or CIDR subnet
       (validated via the stdlib ``ipaddress`` module).
    """
    errors = []

    if not allowed_ips_str or not allowed_ips_str.strip():
        return [], ["Input must not be empty."]

    if not _COMMA_SEP_RE.match(allowed_ips_str):
        return [], [
            "Malformed list — check for leading/trailing commas, "
            "double commas, or missing separators."
        ]

    valid = []
    for entry in allowed_ips_str.split(","):
        entry = entry.strip()
        try:
            ipaddress.ip_network(entry, strict=False)
            valid.append(entry)
        except ValueError:
            errors.append(f"Invalid IP/subnet: '{entry}'")
    return valid, errors


def _parse_allowed_ips(allowed_ips_str):
    """Parse a comma-separated string of IPs/subnets into a list of ip_network objects."""
    valid, errors = validate_allowed_ips(allowed_ips_str)
    for msg in errors:
        logger.warning("MCP RPC: %s, skipping", msg)
    return [ipaddress.ip_network(entry, strict=False) for entry in valid]


class FilteredXMLRPCServer(SimpleXMLRPCServer):
    """IP-filtered server with separate bounded general/control capacity."""

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

    def __init__(self, addr, allowed_ips_str="127.0.0.1", **kwargs):
        self._allowed_networks = _parse_allowed_ips(allowed_ips_str)
        self._handler_slots = threading.BoundedSemaphore(5)
        self._general_slots = threading.BoundedSemaphore(3)
        self._control_slots = threading.BoundedSemaphore(2)
        self._handler_executor = ThreadPoolExecutor(
            max_workers=5, thread_name_prefix="FreeCADMCP-RPC"
        )
        self._accepting_requests = True
        self._accepting_lock = threading.Lock()
        self._json_rpc_transport = _JsonRpcTransport(
            self._dispatch_json_rpc,
            result_to_error=_json_rpc_error_from_result,
        )
        self.json_rpc_max_body_bytes = _MAX_JSON_RPC_BYTES
        self.json_rpc_read_timeout_seconds = 5.0
        kwargs.setdefault("requestHandler", McpIdentityRequestHandler)
        super().__init__(addr, **kwargs)

    def _registered_method(self, method):
        if method.startswith("_"):
            raise _JsonRpcError(_JSON_RPC_METHOD_NOT_FOUND, "Method not found")
        function = self.funcs.get(method)
        if function is None:
            function = getattr(getattr(self, "instance", None), method, None)
        if not callable(function):
            raise _JsonRpcError(_JSON_RPC_METHOD_NOT_FOUND, "Method not found")
        return function

    def _validated_json_rpc_params(self, method, params):
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
            raise _JsonRpcError(
                _JSON_RPC_INVALID_PARAMS,
                "Invalid params",
            ) from exc
        return tuple(params)

    def _dispatch_json_rpc(self, method, params):
        method_params = self._validated_json_rpc_params(method, params)
        control = method in self.CONTROL_METHODS
        slots = self._control_slots if control else self._general_slots
        with self._accepting_lock:
            accepting = self._accepting_requests
        if not accepting:
            raise _JsonRpcError(_JSON_RPC_SERVER_STOPPING, "Server stopping")
        if not slots.acquire(blocking=False):
            lane = "control" if control else "general"
            raise _JsonRpcError(
                _JSON_RPC_SERVER_BUSY,
                "Server busy",
                {"reason": "server_busy", "lane": lane},
            )
        try:
            return self._dispatch(method, method_params)
        finally:
            slots.release()

    def _handle_json_rpc_post(self, handler):
        """Serve one JSON-RPC request on the shared listener."""

        handler.close_connection = True
        content_length = handler.headers.get("Content-Length")
        if content_length is None:
            handler.send_error(411)
            return
        try:
            length = int(content_length)
        except ValueError:
            handler.send_error(400)
            return
        if length < 0:
            handler.send_error(400)
            return
        if length > self.json_rpc_max_body_bytes:
            handler.send_error(413)
            return
        try:
            handler.connection.settimeout(self.json_rpc_read_timeout_seconds)
            payload = handler.rfile.read(length)
        except OSError:
            handler.send_error(408)
            return
        if len(payload) != length:
            handler.send_error(400)
            return
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

    def process_request(self, request, client_address):
        with self._accepting_lock:
            admitted = self._accepting_requests and self._handler_slots.acquire(False)
        if not admitted:
            self.shutdown_request(request)
            return
        try:
            request.settimeout(self.json_rpc_read_timeout_seconds)
            self._handler_executor.submit(
                self._process_request_in_pool, request, client_address
            )
        except Exception:
            self._handler_slots.release()
            self.shutdown_request(request)
            raise

    def _process_request_in_pool(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)
            self._handler_slots.release()

    def _marshaled_dispatch(self, data, dispatch_method=None, path=None):
        """Route parsed XML-RPC methods through independent bounded slots."""
        try:
            _params, method = xmlrpc_loads(data)
        except Exception:
            return super()._marshaled_dispatch(data, dispatch_method, path)
        control = method in self.CONTROL_METHODS
        slots = self._control_slots if control else self._general_slots
        with self._accepting_lock:
            accepting = self._accepting_requests
        if not accepting:
            return xmlrpc_dumps(
                Fault(503, "server_stopping"),
                methodresponse=True,
                allow_none=self.allow_none,
                encoding=self.encoding,
            ).encode(self.encoding, "xmlcharrefreplace")
        if not slots.acquire(blocking=False):
            lane = "control" if control else "general"
            return xmlrpc_dumps(
                Fault(503, f"server_busy: {lane} request capacity is full"),
                methodresponse=True,
                allow_none=self.allow_none,
                encoding=self.encoding,
            ).encode(self.encoding, "xmlcharrefreplace")
        try:
            dispatch = dispatch_method or self._dispatch

            def dispatch_with_safe_response(method_name, method_params):
                return xmlrpc_safe_response(dispatch(method_name, method_params))

            return super()._marshaled_dispatch(data, dispatch_with_safe_response, path)
        finally:
            slots.release()

    def begin_shutdown(self):
        with self._accepting_lock:
            self._accepting_requests = False
        self._json_rpc_transport.begin_shutdown()

    def server_close(self):
        self.begin_shutdown()
        super().server_close()
        self._handler_executor.shutdown(wait=True, cancel_futures=False)

    def verify_request(self, request, client_address):
        client_ip = client_address[0]
        try:
            addr = ipaddress.ip_address(client_ip)
            for network in self._allowed_networks:
                if addr in network:
                    return True
        except ValueError:
            pass
        logger.warning("MCP RPC: rejected connection from %s", client_ip)
        return False
