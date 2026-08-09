"""Compatibility adapter for the canonical bounded JSON-RPC listener."""

try:
    from ..transport.ip_filter import _parse_allowed_ips, validate_allowed_ips
    from ..transport.listener import JsonRpcListener, xmlrpc_safe_response
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from transport.ip_filter import _parse_allowed_ips, validate_allowed_ips
    from transport.listener import JsonRpcListener, xmlrpc_safe_response

from .xmlrpc_identity_handler import McpIdentityRequestHandler

__all__ = [
    "FilteredXMLRPCServer",
    "_parse_allowed_ips",
    "validate_allowed_ips",
    "xmlrpc_safe_response",
]


class FilteredXMLRPCServer(JsonRpcListener):
    """Preserve the legacy listener constructor and request-identity adapter."""

    def __init__(self, addr, allowed_ips_str="127.0.0.1", **kwargs):
        kwargs.setdefault("requestHandler", McpIdentityRequestHandler)
        super().__init__(addr, allowed_ips_str=allowed_ips_str, **kwargs)
