"""Compatibility imports for the canonical JSON-RPC transport."""

try:
    from ..transport.json_rpc_transport import JsonRpcError, JsonRpcTransport
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from transport.json_rpc_transport import JsonRpcError, JsonRpcTransport

__all__ = ["JsonRpcError", "JsonRpcTransport"]
