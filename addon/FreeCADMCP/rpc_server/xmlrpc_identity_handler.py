"""JSON-RPC identity handler with a bounded XML-RPC retirement route."""

import contextlib
import json
from xmlrpc.server import SimpleXMLRPCRequestHandler


def _import_document_lock():
    """Import document_lock under FreeCAD (addon on path) or unit-test package path."""
    try:
        import document_lock as mod

        return mod
    except ImportError:
        from addon.FreeCADMCP import document_lock as mod

        return mod


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
        document_lock = _import_document_lock()
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
        generation_raw = headers.get("X-MCP-Lease-Generation")
        try:
            lease_generation = (
                int(generation_raw) if generation_raw not in (None, "") else None
            )
        except (TypeError, ValueError):
            lease_generation = None
        credential_header = headers.get("X-MCP-Lease-Credentials") or ""
        lease_credentials = []
        if credential_header:
            if len(credential_header) > 32768:
                raise ValueError("lease credential header is too large")
            parsed_credentials = json.loads(credential_header)
            if not isinstance(parsed_credentials, list) or len(parsed_credentials) > 32:
                raise ValueError("lease credential header is invalid")
            lease_credentials = [
                item for item in parsed_credentials if isinstance(item, dict)
            ]
        document_lock.set_request_identity(
            instance_id=headers.get("X-MCP-Instance-Id") or None,
            client=headers.get("X-MCP-Client") or None,
            pid=pid,
            host=headers.get("X-MCP-Host") or None,
            lease_token=headers.get("X-MCP-Lease-Token") or None,
            rpc_port=rpc_port,
            request_id=headers.get("X-MCP-Request-Id") or None,
            rpc_session_token=headers.get("X-MCP-Session-Token") or None,
            lease_id=headers.get("X-MCP-Lease-Id") or None,
            lease_generation=lease_generation,
            document_session_uuid=(
                headers.get("X-MCP-Document-Session-Id") or None
            ),
            lease_credentials=lease_credentials,
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
                _import_document_lock().clear_request_identity()
