"""Bounded-capacity IP-filtered XML-RPC server."""

import ipaddress
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from xmlrpc.client import Fault
from xmlrpc.client import dumps as xmlrpc_dumps
from xmlrpc.client import loads as xmlrpc_loads
from xmlrpc.server import SimpleXMLRPCServer

from .xmlrpc_identity_handler import McpIdentityRequestHandler

logger = logging.getLogger("FreeCADMCP.rpc_server")

_XMLRPC_INT_MIN = -(2**31)
_XMLRPC_INT_MAX = (2**31) - 1

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
        kwargs.setdefault("requestHandler", McpIdentityRequestHandler)
        super().__init__(addr, **kwargs)

    def process_request(self, request, client_address):
        with self._accepting_lock:
            admitted = self._accepting_requests and self._handler_slots.acquire(False)
        if not admitted:
            self.shutdown_request(request)
            return
        try:
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

    def server_close(self):
        self.begin_shutdown()
        super().server_close()
        self._handler_executor.shutdown(wait=False, cancel_futures=False)

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
