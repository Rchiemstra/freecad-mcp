"""RPC request handler that captures MCP identity headers."""

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
    """Capture MCP identity / lease headers for both RPC encodings."""

    def do_POST(self):
        try:
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
                if (
                    not isinstance(parsed_credentials, list)
                    or len(parsed_credentials) > 32
                ):
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
        except Exception:
            pass
        try:
            if self.path == "/jsonrpc":
                return self.server._handle_json_rpc_post(self)
            return super().do_POST()
        finally:
            with contextlib.suppress(Exception):
                _import_document_lock().clear_request_identity()
