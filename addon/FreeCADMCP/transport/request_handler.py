"""HTTP request handling for the JSON-RPC listener."""

from __future__ import annotations

import contextlib
import json
from typing import Any
from xmlrpc.server import SimpleXMLRPCRequestHandler

__all__ = ["JsonRpcRequestHandler"]


def _optional_callback(server: Any, name: str) -> Any:
    callback = getattr(server, name, None)
    return callback if callable(callback) else None


class JsonRpcRequestHandler(SimpleXMLRPCRequestHandler):
    """Route JSON-RPC HTTP requests without locating application state."""

    def send_response(self, code: int, message: str | None = None) -> None:
        super().send_response(code, message)
        header = getattr(self.server, "json_rpc_protocol_header", None)
        value = getattr(self.server, "json_rpc_protocol_value", None)
        if header and value and getattr(self, "path", "") in {
            "/",
            "/RPC2",
            getattr(self.server, "json_rpc_http_path", "/jsonrpc"),
        }:
            self.send_header(header, value)

    def _request_identity(self) -> dict[str, Any]:
        headers = self.headers
        pid_raw = headers.get("X-MCP-Pid")
        port_raw = headers.get("X-MCP-Rpc-Port")
        generation_raw = headers.get("X-MCP-Lease-Generation")
        try:
            pid = int(pid_raw) if pid_raw not in (None, "") else None
        except (TypeError, ValueError):
            pid = None
        try:
            rpc_port = int(port_raw) if port_raw not in (None, "") else None
        except (TypeError, ValueError):
            rpc_port = None
        try:
            lease_generation = (
                int(generation_raw) if generation_raw not in (None, "") else None
            )
        except (TypeError, ValueError):
            lease_generation = None

        credential_header = headers.get("X-MCP-Lease-Credentials") or ""
        lease_credentials: list[dict[str, Any]] = []
        if credential_header:
            if len(credential_header) > 32768:
                raise ValueError("lease credential header is too large")
            parsed_credentials = json.loads(credential_header)
            if not isinstance(parsed_credentials, list) or len(parsed_credentials) > 32:
                raise ValueError("lease credential header is invalid")
            lease_credentials = [
                item for item in parsed_credentials if isinstance(item, dict)
            ]

        return {
            "instance_id": headers.get("X-MCP-Instance-Id") or None,
            "client": headers.get("X-MCP-Client") or None,
            "pid": pid,
            "host": headers.get("X-MCP-Host") or None,
            "lease_token": headers.get("X-MCP-Lease-Token") or None,
            "rpc_port": rpc_port,
            "request_id": headers.get("X-MCP-Request-Id") or None,
            "rpc_session_token": headers.get("X-MCP-Session-Token") or None,
            "lease_id": headers.get("X-MCP-Lease-Id") or None,
            "lease_generation": lease_generation,
            "document_session_uuid": (
                headers.get("X-MCP-Document-Session-Id") or None
            ),
            "lease_credentials": lease_credentials,
        }

    def _capture_request_identity(self) -> None:
        callback = _optional_callback(self.server, "capture_request_identity")
        if callback is not None:
            callback(**self._request_identity())

    def _clear_request_identity(self) -> None:
        callback = _optional_callback(self.server, "clear_request_identity")
        if callback is not None:
            callback()

    def do_POST(self) -> None:
        if self.path in {"/", "/RPC2"}:
            self.server._handle_xmlrpc_retired_post(self)
            return
        if self.path != getattr(self.server, "json_rpc_http_path", "/jsonrpc"):
            self.server._cancel_request_deadline(self.connection)
            self.close_connection = True
            self.send_error(404)
            return

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
            self.server._handle_json_rpc_protocol_mismatch(self)
            return

        payload = self.server._read_json_rpc_post(self)
        if payload is None:
            return
        with contextlib.suppress(Exception):
            self._capture_request_identity()
        try:
            self.server._handle_json_rpc_post(self, payload)
        finally:
            with contextlib.suppress(Exception):
                self._clear_request_identity()
