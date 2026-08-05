"""JSON-RPC identity handler with a bounded XML-RPC retirement route."""

import contextlib
from dataclasses import dataclass
from typing import Any
from xmlrpc.server import SimpleXMLRPCRequestHandler


@dataclass(frozen=True, slots=True)
class IdentityHandlerBindings:
    set_request_identity: Any
    clear_request_identity: Any


_bindings: IdentityHandlerBindings | None = None


def bind_identity_handler(bindings: IdentityHandlerBindings) -> None:
    if not isinstance(bindings, IdentityHandlerBindings):
        raise TypeError("bindings must be IdentityHandlerBindings")
    global _bindings
    _bindings = bindings


def _identity_bindings():
    """Return the narrow authentication-identity bindings from the root."""
    if _bindings is None:
        raise RuntimeError("identity handler collaborators are not initialized")
    return _bindings


class McpIdentityRequestHandler(SimpleXMLRPCRequestHandler):
    """Capture JSON-RPC identity headers and reject retired XML-RPC routes."""

    def send_response(self, code, message=None):
        super().send_response(code, message)
        header = getattr(self.server, "json_rpc_protocol_header", None)
        value = getattr(self.server, "json_rpc_protocol_value", None)
        if header and value and getattr(self, "path", "") in {
            "/",
            "/RPC2",
            getattr(self.server, "json_rpc_http_path", "/jsonrpc"),
        }:
            self.send_header(header, value)

    def _capture_request_identity(self):
        identity = _identity_bindings()
        headers = self.headers
        pid_raw = headers.get("X-MCP-Pid")
        port_raw = headers.get("X-MCP-Rpc-Port")
        try:
            pid = int(pid_raw) if pid_raw not in (None, "") else None
        except (TypeError, ValueError):
            pid = None
        try:
            rpc_port = int(port_raw) if port_raw not in (None, "") else None
        except (TypeError, ValueError):
            rpc_port = None
        identity.set_request_identity(
            instance_id=headers.get("X-MCP-Instance-Id") or None,
            client=headers.get("X-MCP-Client") or None,
            pid=pid,
            host=headers.get("X-MCP-Host") or None,
            rpc_port=rpc_port,
            request_id=headers.get("X-MCP-Request-Id") or None,
            rpc_session_token=headers.get("X-MCP-Session-Token") or None,
        )

    def do_POST(self):
        if self.path in {"/", "/RPC2"}:
            return self.server._handle_xmlrpc_retired_post(self)
        if self.path != getattr(self.server, "json_rpc_http_path", "/jsonrpc"):
            self.server._cancel_request_deadline(self.connection)
            self.close_connection = True
            self.send_error(404)
            return None
        protocol_header = getattr(
            self.server,
            "json_rpc_protocol_header",
            "X-FreeCAD-MCP-Protocol",
        )
        requested_protocols = self.headers.get_all(protocol_header, [])
        expected_protocol = getattr(
            self.server,
            "json_rpc_protocol_value",
            "jsonrpc-2.0",
        )
        if len(requested_protocols) > 1 or (
            requested_protocols and requested_protocols[0] != expected_protocol
        ):
            return self.server._handle_json_rpc_protocol_mismatch(self)
        payload = self.server._read_json_rpc_post(self)
        if payload is None:
            return None
        with contextlib.suppress(Exception):
            self._capture_request_identity()
        try:
            return self.server._handle_json_rpc_post(self, payload)
        finally:
            with contextlib.suppress(Exception):
                _identity_bindings().clear_request_identity()
